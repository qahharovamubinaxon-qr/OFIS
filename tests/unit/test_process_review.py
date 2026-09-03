"""ОБРАБОТКА (AI mode) — read on upload, check, then print from the boxes.

The main screen read the passport and patent and printed in one press. A
misread name went onto the employment package unseen. It now reads on drop,
shows editable boxes, and prints from what is IN THE BOXES — the manual and
ZIP paths are untouched.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender
from src.ui.i18n import Translator

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _company():
    return SimpleNamespace(id="c1", name="ООО РОГА И КОПЫТА")


class _Controller:
    def __init__(self, passport, patent) -> None:
        self._passport, self._patent = passport, patent
        self.printed: dict = {}

    def companies(self):
        return [_company()]

    def ai_available(self) -> bool:
        return True

    def next_reg_number(self) -> int:
        return 42

    def read_image(self, path):
        return b"img"

    def read_documents(self, passport, patent, patent_back):
        return self._passport, self._patent

    def generate(self, company, passport, patent, *, form_date, profession):
        self.printed = {"company": company, "passport": passport,
                        "patent": patent, "form_date": form_date,
                        "profession": profession}
        return SimpleNamespace(pdf_path=Path("OUT.pdf"), reg_number=42)


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.process_view as pv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001 - the view's own error path
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(pv, "run_async", run_now)
    return pv


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
    screen = view_mod.ProcessView(controller, Translator())
    screen._done = lambda result: None
    return screen, controller


def test_the_panel_is_hidden_until_read(view) -> None:
    screen, _ = _make(view, *_worker())
    assert screen._review.isHidden()


def test_dropping_reads_and_shows_the_worker(view) -> None:
    screen, _ = _make(view, *_worker())
    screen._dz_passport = _Drop("p.jpg")
    screen._read_now()
    assert not screen._review.isHidden()
    assert screen._review._boxes["surname"].text() == "ПАЛВАНОВ"   # patent, Russian


def test_run_prints_the_boxes_not_the_raw_read(view) -> None:
    screen, controller = _make(view, *_worker())
    screen._dz_passport = _Drop("p.jpg")
    screen._read_now()
    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    screen._run_ai()
    assert controller.printed["passport"].surname == "ПАЛВАНОВА"
    assert controller.printed["patent"] is None      # folded into the passport


def test_run_refuses_before_read(view) -> None:
    from PySide6.QtWidgets import QMessageBox

    screen, controller = _make(view, *_worker())
    QMessageBox.warning = staticmethod(lambda *a: None)
    screen._dz_passport = _Drop(None)
    screen._run_ai()
    assert not controller.printed


def test_the_bot_one_shot_path_stays() -> None:
    from src.controllers.process_controller import ProcessController

    assert hasattr(ProcessController, "generate_from_images")
    assert hasattr(ProcessController, "read_documents")
    assert hasattr(ProcessController, "generate")
