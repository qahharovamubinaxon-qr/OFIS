"""УНИВЕРСАЛ — read the worker's documents on drop, check the ФИО, then fill.

The universal filler read the dropped documents and filled the template in one
press. It now reads on drop and shows the ФИО in the shared check panel; the
template is filled from what is IN THE BOXES.
"""

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


class _Ocr:
    def __init__(self, passport, patent) -> None:
        self._passport, self._patent = passport, patent

    def available(self) -> bool:
        return True

    def read_documents(self, a, b=None, c=None):
        return self._passport, self._patent


class _Svc:
    def __init__(self) -> None:
        self.seen: dict = {}

    def generate(self, source, passport, patent, *, form_date):
        self.seen = {"source": source, "passport": passport, "patent": patent}
        return SimpleNamespace(pdf_path=Path("OUT.pdf"), replacements=3,
                               surname=passport.surname)


class _Templates:
    def list(self):
        return []


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.umumiy_view as uv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001 - the view's own error path
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(uv, "run_async", run_now)
    return uv


class _File:
    """A dropped file whose bytes are canned — no disk needed."""

    def __init__(self, name="passport.jpg") -> None:
        self.name = name

    def read_bytes(self) -> bytes:
        return b"img"


class _MultiDrop:
    def __init__(self, files=None) -> None:
        self.files = list(files or [])

    def clear_files(self) -> None:
        self.files = []


def _worker():
    passport = Passport(
        surname="PALVANOV", name="DOVLETGELDI", number="046688",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE,
        birth_date=date(1990, 5, 15))
    patent = Patent(number="240", profession="рабочий",
                    holder_surname="ПАЛВАНОВ", holder_name="ДОВЛЕТГЕЛДИ",
                    holder_citizenship="ТУРКМЕНИСТАН")
    return passport, patent


def _make(view_mod):
    passport, patent = _worker()
    svc = _Svc()
    screen = view_mod.UmumiyView(_Ocr(passport, patent), svc, _Templates())
    screen._done = lambda r: None
    return screen, svc


def test_the_panel_is_hidden_until_read(view) -> None:
    screen, _ = _make(view)
    assert screen._review.isHidden()


def test_dropping_reads_and_shows_the_worker(view) -> None:
    screen, _ = _make(view)
    screen._dz_worker = _MultiDrop([_File("passport.jpg")])
    screen._read_now()
    assert not screen._review.isHidden()
    assert screen._review._boxes["surname"].text() == "ПАЛВАНОВ"


def test_run_fills_from_the_boxes(view) -> None:
    screen, svc = _make(view)
    screen._dz_worker = _MultiDrop([_File("passport.jpg")])
    screen._read_now()
    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    screen._dz_doc = _MultiDrop([_File("blank.pdf")])   # the source document
    screen._run_ai()
    assert svc.seen["passport"].surname == "ПАЛВАНОВА"
    # the corrected name rides the patent too
    assert svc.seen["patent"].holder_surname == "ПАЛВАНОВА"
