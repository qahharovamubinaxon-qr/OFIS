"""ИНН — read, show, correct, then print from the boxes.

The ИНН sheet prints the worker's ФИО, sex, birth date and citizenship. They
used to be read only INSIDE the print step, so a misread name went onto a
filed record unseen. Now the passport is read the moment it is dropped, shown
in editable boxes beside the ИНН number, and the sheet is printed from what is
in them.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from src.domain.documents import Passport
from src.domain.enums import Gender

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class _Controller:
    def __init__(self, passport, inn_digits="") -> None:
        self._passport, self._inn = passport, inn_digits
        self.printed: dict = {}

    def ai_available(self) -> bool:
        return True

    def read_all(self, image):
        return self._passport, self._inn

    def generate(self, passport, *, inn, form_date):
        self.printed = {"passport": passport, "inn": inn, "date": form_date}

        class _Result:
            pdf_path = Path("OUT.pdf")
            surname = passport.surname
            inn = "1" * 12

        return _Result()


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.inn_view as iv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(iv, "run_async", run_now)
    return iv


class _Drop:
    def __init__(self, path=None) -> None:
        self.path = path

    def clear(self) -> None:
        self.path = None


@pytest.fixture
def jpg(tmp_path) -> str:
    """A real file on disk — the ИНН view reads the dropped path itself."""
    p = tmp_path / "doc.jpg"
    p.write_bytes(b"\xff\xd8fake-jpeg")
    return str(p)


def _worker() -> Passport:
    return Passport(surname="ИСОЕВ", name="АСЛИДИН", patronymic="ХОЛБЕРДИЕВИЧ",
                    number="405847273", nationality="ТАДЖИКИСТАН",
                    gender=Gender.MALE, birth_date=date(1999, 7, 25))


def _make(view_mod, passport, inn_digits=""):
    controller = _Controller(passport, inn_digits)
    screen = view_mod.InnView(controller)
    screen._done = lambda result: None
    return screen, controller


# --------------------------------------------------------- read and show
def test_the_boxes_are_hidden_until_something_is_read(view) -> None:
    screen, _ = _make(view, _worker())
    assert screen._read.isHidden()


def test_dropping_the_document_shows_the_worker(view, jpg) -> None:
    screen, _ = _make(view, _worker())
    screen._dz = _Drop(jpg)
    screen._read_now()
    assert not screen._read.isHidden()
    assert screen._boxes["surname"].text() == "ИСОЕВ"
    assert screen._boxes["citizenship"].text() == "ТАДЖИКИСТАН"
    assert screen._gender.currentText() == "Мужской"
    assert screen._born.date().toString("dd.MM.yyyy") == "25.07.1999"


def test_the_inn_is_filled_when_found_on_the_document(view, jpg) -> None:
    screen, _ = _make(view, _worker(), inn_digits="770712345678")
    screen._dz = _Drop(jpg)
    screen._read_now()
    assert screen._inn.text() == "770712345678"


def test_a_typed_inn_is_never_overwritten_by_the_reader(view, jpg) -> None:
    screen, _ = _make(view, _worker(), inn_digits="770712345678")
    screen._inn.setText("111111111111")
    screen._dz = _Drop(jpg)
    screen._read_now()
    assert screen._inn.text() == "111111111111"


# ----------------------------------------------------- print from the boxes
def test_run_prints_the_corrected_name(view, jpg) -> None:
    screen, controller = _make(view, _worker(), inn_digits="770712345678")
    screen._dz = _Drop(jpg)
    screen._read_now()
    screen._boxes["surname"].setText("ИСОЕВА")     # operator fixes a misread
    screen._run_ai()
    assert controller.printed["passport"].surname == "ИСОЕВА"
    assert controller.printed["inn"] == "770712345678"


def test_run_refuses_a_short_inn(view, jpg) -> None:
    from PySide6.QtWidgets import QMessageBox

    screen, controller = _make(view, _worker(), inn_digits="")
    screen._dz = _Drop(jpg)
    screen._read_now()
    screen._inn.setText("123")
    warned = []
    QMessageBox.information = staticmethod(lambda *a: warned.append(a))
    screen._run_ai()
    assert warned and not controller.printed


def test_run_refuses_before_anything_is_read(view) -> None:
    from PySide6.QtWidgets import QMessageBox

    screen, controller = _make(view, _worker())
    screen._dz = _Drop(None)
    warned = []
    QMessageBox.information = staticmethod(lambda *a: warned.append(a))
    screen._run_ai()
    assert warned and not controller.printed


def test_a_failed_read_still_opens_the_boxes(view, jpg) -> None:
    from src.common.errors import OfisError

    screen, _ = _make(view, _worker())
    screen._c.read_all = lambda *a: (_ for _ in ()).throw(OfisError("AI йўқ"))
    screen._dz = _Drop(jpg)
    screen._read_now()
    assert not screen._read.isHidden()


def test_the_bot_path_is_untouched() -> None:
    from src.controllers.inn_controller import InnController

    assert hasattr(InnController, "generate_from_image")
    assert hasattr(InnController, "read_all")
    assert hasattr(InnController, "generate")
