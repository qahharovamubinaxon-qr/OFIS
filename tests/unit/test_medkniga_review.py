"""МЕД КНИЖКА — read on upload, check the ФИО, then print the four pages.

The med book read the passport (or a patent) and printed in one press. It now
reads on drop and shows the ФИО in editable boxes; a patent-only book is shown
through a stand-in passport so the same check panel works. Printing is from
what is IN THE BOXES.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.domain.documents import Passport
from src.domain.enums import Gender

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class _Controller:
    def __init__(self, passport) -> None:
        self._passport = passport
        self.printed: dict = {}

    def kits(self):
        return {"standard": "Стандарт"}

    def next_number(self):
        return "0001"

    def ai_available(self) -> bool:
        return True

    def read_image(self, path):
        return b"img"

    def read_document(self, data, *, is_patent=False):
        self.read_as_patent = is_patent
        return self._passport

    def print_document(self, passport, *, position, city, number, exam_date,
                       photo_png=None, signature_png=None, kit="standard"):
        self.printed = {"passport": passport, "position": position,
                        "city": city, "number": number, "kit": kit}
        return SimpleNamespace(pdf_path=Path("OUT.pdf"), number=number,
                               exam_date=exam_date, expires=exam_date)


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.medkniga_view as mv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001 - the view's own error path
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(mv, "run_async", run_now)
    return mv


class _Drop:
    def __init__(self, path=None) -> None:
        self.path = path

    def clear(self) -> None:
        self.path = None


def _passport():
    return Passport(
        surname="PALVANOV", name="DOVLETGELDI", number="046688", series="A2",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE,
        birth_date=date(1990, 5, 15), issue_date=date(2023, 3, 13),
        expiry_date=date(2028, 3, 12))


def _make(view_mod, passport):
    controller = _Controller(passport)
    screen = view_mod.MedKnigaView(controller)
    screen._done = lambda result: None
    return screen, controller


def test_the_panel_is_hidden_until_read(view) -> None:
    screen, _ = _make(view, _passport())
    assert screen._review.isHidden()


def test_dropping_reads_and_shows_the_fio(view) -> None:
    screen, _ = _make(view, _passport())
    screen._document = _Drop("passport.jpg")
    screen._read_now()
    assert not screen._review.isHidden()
    assert screen._review._boxes["surname"].text() == "PALVANOV"


def test_a_patent_named_file_reads_as_a_patent(view) -> None:
    screen, controller = _make(view, _passport())
    screen._document = _Drop("патент.jpg")
    screen._read_now()
    assert controller.read_as_patent is True


def test_run_prints_the_boxes(view) -> None:
    screen, controller = _make(view, _passport())
    screen._document = _Drop("p.jpg")
    screen._read_now()
    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    screen._number.setText("777")
    screen._generate()
    assert controller.printed["passport"].surname == "ПАЛВАНОВА"
    assert controller.printed["number"] == "777"


def test_the_one_shot_path_stays() -> None:
    from src.controllers.medkniga_controller import MedKnigaController

    assert hasattr(MedKnigaController, "generate_from_images")
    assert hasattr(MedKnigaController, "read_document")
    assert hasattr(MedKnigaController, "print_document")


def test_a_stand_in_passport_carries_the_patent_fio() -> None:
    from src.controllers.medkniga_controller import _passport_from_patent

    patent = SimpleNamespace(holder_surname="ПАЛВАНОВ", holder_name="ДОВЛЕТ",
                             holder_patronymic="БАЙРАМОВИЧ",
                             holder_citizenship="ТУРКМЕНИСТАН")
    stand_in = _passport_from_patent(patent)
    assert stand_in.surname == "ПАЛВАНОВ"
    assert stand_in.nationality == "ТУРКМЕНИСТАН"
