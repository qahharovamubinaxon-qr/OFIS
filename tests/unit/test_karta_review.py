"""КАРТА — read, show, correct, then print onto the laminated card.

The foreigner's ID card prints the worker's ФИО, sex, birth date and
citizenship. They used to be read INSIDE the print step, so a misread name
went onto a card — laminated, hard to remake — with nobody having seen it.
Now the passport is read on drop, shown in editable boxes, and the card is
printed from what is in them.
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
    def __init__(self, passport) -> None:
        self._passport = passport
        self.printed: dict = {}

    def ai_available(self) -> bool:
        return True

    def blank(self, side: str):
        return Path("blank.pdf")           # both sides present

    def next_numbers(self) -> dict:
        return {"serial": "001", "card_number": "АА0000001",
                "series": "0000001"}

    def layout(self) -> dict:
        return {}

    @staticmethod
    def expiry(issued):
        return issued

    def read_passport(self, image):
        return self._passport

    def generate(self, *, passport, photo, signature, issued, card_code):
        self.printed = {"passport": passport, "code": card_code,
                        "issued": issued}

        class _Result:
            saved = Path("CARD.pdf")
            card_number = card_code

        return _Result()


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.karta_view as kv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(kv, "run_async", run_now)
    return kv


class _Drop:
    def __init__(self, path=None) -> None:
        self.path = path

    def clear(self) -> None:
        self.path = None


@pytest.fixture
def jpg(tmp_path) -> str:
    p = tmp_path / "doc.jpg"
    p.write_bytes(b"\xff\xd8fake-jpeg")
    return str(p)


def _worker() -> Passport:
    return Passport(surname="ИСОЕВ", name="АСЛИДИН", patronymic="ХОЛБЕРДИЕВИЧ",
                    number="405847273", nationality="ТАДЖИКИСТАН",
                    gender=Gender.MALE, birth_date=date(1999, 7, 25))


def _make(view_mod, passport):
    controller = _Controller(passport)
    screen = view_mod.KartaView(controller)
    screen._done = lambda result: None
    return screen, controller


def _ready(screen, jpg) -> None:
    """Drop the passport and read it, so the boxes are showing."""
    screen._passport = _Drop(jpg)
    screen._read_now()


# --------------------------------------------------------- read and show
def test_the_boxes_are_hidden_until_something_is_read(view) -> None:
    screen, _ = _make(view, _worker())
    assert screen._read.isHidden()


def test_dropping_the_passport_shows_the_worker(view, jpg) -> None:
    screen, _ = _make(view, _worker())
    _ready(screen, jpg)
    assert not screen._read.isHidden()
    assert screen._boxes["surname"].text() == "ИСОЕВ"
    assert screen._boxes["patronymic"].text() == "ХОЛБЕРДИЕВИЧ"
    assert screen._gender.currentText() == "Мужской"


# ----------------------------------------------------- print from the boxes
def test_the_card_prints_the_corrected_name(view, jpg) -> None:
    screen, controller = _make(view, _worker())
    _ready(screen, jpg)
    screen._photo = _Drop(jpg)
    screen._code.setText("АВ1563244")
    screen._boxes["surname"].setText("ИСОЕВА")     # operator fixes a misread
    screen._generate()
    assert controller.printed["passport"].surname == "ИСОЕВА"
    assert controller.printed["code"] == "АВ1563244"


def test_the_card_is_not_printed_before_the_passport_is_read(view, jpg) -> None:
    screen, controller = _make(view, _worker())
    screen._photo = _Drop(jpg)
    screen._code.setText("АВ1563244")
    screen._passport = _Drop(None)
    screen._generate()
    assert not controller.printed           # warned, nothing printed


def test_a_blank_surname_is_refused(view, jpg) -> None:
    screen, controller = _make(view, _worker())
    _ready(screen, jpg)
    screen._photo = _Drop(jpg)
    screen._code.setText("АВ1563244")
    screen._boxes["surname"].clear()
    screen._generate()
    assert not controller.printed


def test_a_failed_read_still_opens_the_boxes(view, jpg) -> None:
    from src.common.errors import OfisError

    screen, _ = _make(view, _worker())
    screen._c.read_passport = lambda *a: (_ for _ in ()).throw(
        OfisError("AI йўқ"))
    _ready(screen, jpg)
    assert not screen._read.isHidden()
