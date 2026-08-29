"""ТРУД — read, show, correct, then print the трудовой + уведомление.

The договор prints the worker's whole identity — name, birth, passport. It
used to be read INSIDE the print step, so a misread went onto a filed contract
unseen. Now the documents are read on drop, shown in editable boxes, and the
pair is printed from what is in them. The patent is kept as read: its issue
date sets the contract's end, and the operator does not retype it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class _Firm:
    id = "firm-1"
    name = "ООО СТРОЙ"


class _Controller:
    def __init__(self, passport, patent) -> None:
        self._passport, self._patent = passport, patent
        self.printed: dict = {}

    def ai_available(self) -> bool:
        return True

    def firms(self):
        return [_Firm()]

    def read_image(self, path):
        return b"img"

    def read_documents(self, passport, patent, patent_back):
        return self._passport, self._patent

    def generate(self, firm, passport, patent, *, form_date, profession):
        self.printed = {"firm": firm, "passport": passport, "patent": patent,
                        "date": form_date, "profession": profession}

        class _Result:
            trud_path = Path("T.pdf")
            uved_path = Path("U.pdf")
            hod_path = None
            notes: list = []

        return _Result()


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.trud_view as tv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(tv, "run_async", run_now)
    # RUN ends in a save dialog; skip it
    monkeypatch.setattr("src.ui.widgets.save_to.ask_save_dir",
                        lambda *a, **k: None)
    return tv


class _Drop:
    def __init__(self, path=None) -> None:
        self.path = path

    def clear(self) -> None:
        self.path = None


def _worker():
    passport = Passport(surname="ИСОЕВ", name="АСЛИДИН",
                        patronymic="ХОЛБЕРДИЕВИЧ", number="405847273",
                        series="P", nationality="ТАДЖИКИСТАН",
                        gender=Gender.MALE, birth_date=date(1999, 7, 25),
                        issue_date=date(2025, 1, 18))
    patent = Patent(number="240", profession="рабочий",
                    issue_date=date(2025, 3, 4))
    return passport, patent


def _make(view_mod, passport, patent):
    controller = _Controller(passport, patent)
    screen = view_mod.TrudView(controller)
    screen._selected_firm = lambda: _Firm()
    screen._done = lambda result: None
    return screen, controller


def _read(screen) -> None:
    screen._dz_passport = _Drop("passport.jpg")
    screen._dz_patent = _Drop("patent.jpg")
    screen._dz_patent_back = _Drop(None)
    screen._read_now()


# --------------------------------------------------------- read and show
def test_the_boxes_are_hidden_until_something_is_read(view) -> None:
    screen, _ = _make(view, *_worker())
    assert screen._read.isHidden()


def test_dropping_the_documents_shows_the_worker(view) -> None:
    screen, _ = _make(view, *_worker())
    _read(screen)
    assert not screen._read.isHidden()
    assert screen._boxes["surname"].text() == "ИСОЕВ"
    assert screen._boxes["citizenship"].text() == "ТАДЖИКИСТАН"
    # a Tajik passport's «P» series is folded into the number by the model,
    # so the series box is empty — the same as it is on the ДМС screen
    assert screen._boxes["number"].text() == "405847273"


# ----------------------------------------------------- print from the boxes
def test_run_prints_the_corrected_name(view) -> None:
    screen, controller = _make(view, *_worker())
    _read(screen)
    screen._boxes["surname"].setText("ИСОЕВА")
    screen._run_ai()
    assert controller.printed["passport"].surname == "ИСОЕВА"


def test_the_patent_is_carried_through_for_its_dates(view) -> None:
    """The contract's end is a year on from the patent's issue date, so the
    patent object read off the card must reach the print step."""
    screen, controller = _make(view, *_worker())
    _read(screen)
    screen._run_ai()
    assert controller.printed["patent"] is not None
    assert controller.printed["patent"].issue_date == date(2025, 3, 4)


def test_the_passport_issue_date_survives_even_though_it_has_no_box(view) -> None:
    screen, controller = _make(view, *_worker())
    _read(screen)
    screen._run_ai()
    assert controller.printed["passport"].issue_date == date(2025, 1, 18)


def test_run_refuses_before_anything_is_read(view) -> None:
    from PySide6.QtWidgets import QMessageBox

    screen, controller = _make(view, *_worker())
    screen._dz_passport = _Drop(None)
    warned = []
    QMessageBox.warning = staticmethod(lambda *a: warned.append(a))
    QMessageBox.information = staticmethod(lambda *a: warned.append(a))
    screen._run_ai()
    assert not controller.printed


def test_a_failed_read_still_opens_the_boxes(view) -> None:
    from src.common.errors import OfisError

    screen, _ = _make(view, *_worker())
    screen._c.read_documents = lambda *a: (_ for _ in ()).throw(
        OfisError("AI йўқ"))
    _read(screen)
    assert not screen._read.isHidden()


def test_the_bot_path_is_untouched() -> None:
    from src.controllers.trud_controller import TrudController

    assert hasattr(TrudController, "generate_from_images")
    assert hasattr(TrudController, "read_documents")
    assert hasattr(TrudController, "generate")
