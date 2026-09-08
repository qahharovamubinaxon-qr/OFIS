"""АЛЬЯНСКОТ 2400 screen — read the passport, check the ФИО, print 3 PDFs.

The office drops the passport (read on the spot into the shared check panel),
the worker signs and a photo is dropped, and one press prints the worker onto
all three uploaded blanks. RUN is refused until the passport is read AND all
three blanks are present.
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


@pytest.fixture
def run_now(monkeypatch):
    def _install(module):
        def run(fn, *a, on_success=None, on_error=None, **k):
            try:
                result = fn(*a, **k)
            except Exception as exc:  # noqa: BLE001 - the view's own error path
                if on_error:
                    on_error(exc)
            else:
                if on_success:
                    on_success(result)
        monkeypatch.setattr(module, "run_async", run)
    return _install


class _Drop:
    def __init__(self, path=None) -> None:
        self.path = path

    def clear(self) -> None:
        self.path = None


def _passport() -> Passport:
    return Passport(
        surname="PALVANOV", name="DOVLETGELDI", number="046688", series="A2",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE,
        birth_date=date(1990, 5, 15), issue_date=date(2023, 3, 13),
        expiry_date=date(2028, 3, 12))


class _Ctl:
    """Enough of AllianceController to build the screen and record RUN."""

    def __init__(self, passport) -> None:
        self._passport = passport
        self.printed: dict = {}
        self._blanks: dict[str, Path | None] = {
            "udo": None, "spr1": None, "spr2": None}

    def ai_available(self) -> bool:
        return True

    def read_image(self, path):
        return b"img"

    def read_documents(self, passport_bytes):
        return self._passport

    def blank(self, slot):
        return self._blanks.get(slot)

    def pages(self, slot):
        return 0

    def until(self, start):
        return date(start.year + 3, start.month, start.day) if start else None

    def generate(self, **k):
        self.printed.update(k)
        return [SimpleNamespace(slot=s, saved=Path(f"{s}.pdf"), pdf=b"%PDF")
                for s in ("udo", "spr1", "spr2")]

    def __getattr__(self, name):
        return lambda *a, **k: None


def _screen(run_now, ctl):
    import src.ui.views.alliance_view as av
    run_now(av)
    screen = av.AllianceView(ctl)
    screen._done = lambda r: None
    return screen


def test_dropping_passport_fills_the_review(run_now) -> None:
    ctl = _Ctl(_passport())
    screen = _screen(run_now, ctl)
    screen._passport = _Drop("p.jpg")
    screen._read_now()
    assert not screen._review.isHidden()
    assert screen._review._boxes["surname"].text() == "PALVANOV"


def test_end_date_label_is_start_plus_three_years(run_now) -> None:
    ctl = _Ctl(_passport())
    screen = _screen(run_now, ctl)
    from PySide6.QtCore import QDate
    screen._start.setDate(QDate(2026, 9, 7))
    assert screen._until_label.text() == "07.09.2029"


def test_run_refused_until_all_three_blanks(run_now) -> None:
    ctl = _Ctl(_passport())
    screen = _screen(run_now, ctl)
    screen._passport = _Drop("p.jpg")
    screen._photo = _Drop("ph.jpg")
    screen._signature = b"sig"
    screen._read_now()
    # only udo uploaded → refused
    ctl._blanks["udo"] = Path("u.pdf")
    screen._generate()
    assert not ctl.printed


def test_run_prints_with_corrected_name_and_start(run_now) -> None:
    ctl = _Ctl(_passport())
    screen = _screen(run_now, ctl)
    screen._passport = _Drop("p.jpg")
    screen._photo = _Drop("ph.jpg")
    screen._signature = b"sig"
    screen._read_now()
    screen._review._boxes["surname"].setText("ПАЛВАНОВА")
    for slot in ("udo", "spr1", "spr2"):
        ctl._blanks[slot] = Path(f"{slot}.pdf")
    from PySide6.QtCore import QDate
    screen._start.setDate(QDate(2026, 9, 7))
    screen._ud_number.setText("2400-0145")
    screen._generate()
    assert ctl.printed["passport"].surname == "ПАЛВАНОВА"
    assert ctl.printed["start_date"] == date(2026, 9, 7)
    assert ctl.printed["gender"] in ("Мужской", "Женский")
    assert ctl.printed["ud_number"] == "2400-0145"


def test_run_needs_a_signature(run_now) -> None:
    ctl = _Ctl(_passport())
    screen = _screen(run_now, ctl)
    screen._passport = _Drop("p.jpg")
    screen._photo = _Drop("ph.jpg")
    screen._signature = None
    screen._read_now()
    for slot in ("udo", "spr1", "spr2"):
        ctl._blanks[slot] = Path(f"{slot}.pdf")
    screen._generate()
    assert not ctl.printed
