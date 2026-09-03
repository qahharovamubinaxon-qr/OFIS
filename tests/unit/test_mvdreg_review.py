"""МВД РЕГИСТРАЦИЯ — read on upload, check, then print from the boxes."""

from __future__ import annotations

from datetime import date
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


def _address():
    return SimpleNamespace(id="a1", label="МОСКВА, ПАРКОВАЯ 55",
                           template_path=Path("x.pdf"))


class _Controller:
    def __init__(self, passport, patent) -> None:
        self._passport, self._patent = passport, patent
        self.printed: dict = {}

    def addresses(self):
        return [_address()]

    def ai_available(self) -> bool:
        return True

    def blank(self):
        return SimpleNamespace(name="blank.pdf")

    def asset(self, name, template=None):
        return None

    def read_image(self, path):
        return b"img"

    def read_documents(self, passport, patent, patent_back):
        return self._passport, self._patent

    def generate(self, passport, patent, address, *, registration_expiry,
                 registration_start=None):
        self.printed = {"passport": passport, "patent": patent,
                        "address": address, "expiry": registration_expiry,
                        "start": registration_start}
        return SimpleNamespace(pdf_path=Path("OUT.pdf"))


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.mvdreg_view as mv

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


def _worker():
    passport = Passport(
        surname="PALVANOV", name="DOVLETGELDI", number="046688", series="A2",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE,
        birth_date=date(1990, 5, 15), issue_date=date(2023, 3, 13),
        expiry_date=date(2028, 3, 12))
    patent = Patent(number="240", profession="рабочий",
                    holder_surname="ПАЛВАНОВ", holder_name="ДОВЛЕТГЕЛДИ",
                    holder_patronymic="БАЙРАМОВИЧ",
                    holder_citizenship="ТУРКМЕНИСТАН")
    return passport, patent


def _make(view_mod, passport, patent):
    controller = _Controller(passport, patent)
    screen = view_mod.MvdRegView(controller)
    screen._done = lambda result: None
    return screen, controller


def test_the_panel_is_hidden_until_read(view) -> None:
    screen, _ = _make(view, *_worker())
    assert screen._review.isHidden()


def test_dropping_reads_and_shows_the_worker(view) -> None:
    screen, _ = _make(view, *_worker())
    screen._passport = _Drop("p.jpg")
    screen._read_now()
    assert not screen._review.isHidden()
    assert screen._review._boxes["surname"].text() == "ПАЛВАНОВ"


def test_run_prints_the_boxes(view) -> None:
    screen, controller = _make(view, *_worker())
    screen._passport = _Drop("p.jpg")
    screen._read_now()
    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    screen._generate()
    assert controller.printed["passport"].surname == "ПАЛВАНОВА"
    assert controller.printed["patent"] is None


def test_the_bot_one_shot_path_stays() -> None:
    from src.controllers.mvdreg_controller import MvdRegController

    assert hasattr(MvdRegController, "generate_from_images")
    assert hasattr(MvdRegController, "read_documents")
    assert hasattr(MvdRegController, "generate")
