"""2 НДФЛ — read on upload, check, then print from the boxes.

The справка read the passport and patent and printed in one press. It now
reads on drop, shows editable boxes (the ИНН read off the patent is kept
aside for the form), and prints from what is IN THE BOXES.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class _Controller:
    def __init__(self, passport, patent, inn) -> None:
        self._passport, self._patent, self._inn = passport, patent, inn
        self.printed: dict = {}

    def firms(self):
        return [Path("firm_a.pdf")]

    def ai_available(self) -> bool:
        return True

    def read_image(self, path):
        return b"img"

    def read_documents(self, passport, patent):
        return self._passport, self._patent, self._inn

    def generate(self, firm, passport, *, months, year, form_date=None, inn=""):
        self.printed = {"firm": firm, "passport": passport, "months": months,
                        "year": year, "form_date": form_date, "inn": inn}
        return SimpleNamespace(pdf_path=Path("OUT.pdf"),
                               total=Decimal("10000"), tax=Decimal("1300"))


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.ndfl2_view as nv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001 - the view's own error path
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(nv, "run_async", run_now)
    return nv


class _Drop:
    def __init__(self, path=None) -> None:
        self.path = path

    def clear(self) -> None:
        self.path = None


def _worker():
    passport = Passport(
        surname="PALVANOV", name="DOVLETGELDI", number="046688", series="A2",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE,
        birth_date=date(1990, 5, 15), issue_date=date(2023, 3, 13),
        expiry_date=date(2028, 3, 12))
    patent = Patent(number="240", profession="рабочий",
                    holder_surname="ПАЛВАНОВ", holder_name="ДОВЛЕТГЕЛДИ",
                    holder_citizenship="ТУРКМЕНИСТАН")
    return passport, patent


def _make(view_mod, passport, patent, inn="770123456789"):
    controller = _Controller(passport, patent, inn)
    screen = view_mod.Ndfl2View(controller)
    screen._done = lambda result: None
    return screen, controller


def test_the_panel_is_hidden_until_read(view) -> None:
    screen, _ = _make(view, *_worker())
    assert screen._review.isHidden()


def test_dropping_reads_shows_and_keeps_the_inn(view) -> None:
    screen, _ = _make(view, *_worker())
    screen._passport = _Drop("p.jpg")
    screen._patent = _Drop("pat.jpg")
    screen._read_now()
    assert not screen._review.isHidden()
    assert screen._review._boxes["surname"].text() == "ПАЛВАНОВ"
    assert screen._inn == "770123456789"


def test_run_prints_the_boxes_and_the_kept_inn(view) -> None:
    screen, controller = _make(view, *_worker())
    screen._passport = _Drop("p.jpg")
    screen._read_now()
    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    screen._months[0].setText("10000")
    screen._generate()
    assert controller.printed["passport"].surname == "ПАЛВАНОВА"
    assert controller.printed["inn"] == "770123456789"
    assert controller.printed["months"] == {1: Decimal("10000")}


def test_the_one_shot_path_stays() -> None:
    from src.controllers.ndfl2_controller import Ndfl2Controller

    assert hasattr(Ndfl2Controller, "generate_from_images")
    assert hasattr(Ndfl2Controller, "read_documents")
    assert hasattr(Ndfl2Controller, "generate")
