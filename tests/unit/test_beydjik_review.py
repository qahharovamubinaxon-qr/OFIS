"""БЕЙДЖИК / ПАТЕНТ — read the passport on drop, check, then print the badge.

БЕЙДЖИК (and ПАТЕНТ, which is the same screen on the patent blanks) read the
passport and printed the badge in one press, so a misread ФИО went onto the
card unseen. The office asked for the read-then-check flow here too: drop the
passport, it reads at once and shows the values in editable boxes, and the
badge is printed from what is IN THE BOXES.
"""

from __future__ import annotations

from datetime import date

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

    def regions(self):
        return [("77", "77 · Москва"), ("50", "50 · Московская область")]

    def territory(self, code):
        return "г. Москва"

    def next_pr(self):
        return "4875056"

    def set_next_pr(self, value):
        pass

    def firm(self):
        return ""

    def firms(self):
        return []

    def read_image(self, path):
        return b"img"

    def read_passport(self, data):
        return self._passport

    def generate(self, passport, **kw):
        self.printed = {"passport": passport, **kw}

        class _Result:
            surname = passport.surname
            pr_number = "4875056"
            region = kw.get("region", "77")
            pdf_path = __import__("pathlib").Path("OUT.pdf")

        return _Result()


@pytest.fixture
def view(monkeypatch):
    import src.ui.views.beydjik_view as bv

    def run_now(fn, *a, on_success=None, on_error=None, **k):
        try:
            result = fn(*a, **k)
        except Exception as exc:  # noqa: BLE001 - the view's own error path
            if on_error:
                on_error(exc)
        else:
            if on_success:
                on_success(result)

    monkeypatch.setattr(bv, "run_async", run_now)
    return bv


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


def _make(view_mod, passport):
    controller = _Controller(passport)
    screen = view_mod.BeydjikView(controller)
    screen._done = lambda result: None            # skip the folder button state
    return screen, controller


def test_the_panel_is_hidden_until_something_is_read(view) -> None:
    screen, _ = _make(view, _passport())
    assert screen._review.isHidden()


def test_dropping_the_passport_reads_and_shows_it(view) -> None:
    screen, _ = _make(view, _passport())
    screen._passport = _Drop("passport.jpg")
    screen._read_now()
    assert not screen._review.isHidden()
    assert screen._review._boxes["surname"].text() == "PALVANOV"
    assert screen._review._boxes["number"].text() == "046688"


def test_the_badge_prints_what_is_in_the_boxes(view) -> None:
    screen, controller = _make(view, _passport())
    screen._passport = _Drop("p.jpg")
    screen._read_now()
    screen._review._boxes["surname"].setText("ПАЛВАНОВ")   # operator corrects
    screen._personal.setText("2600263521")
    screen._run_ai()
    assert controller.printed["passport"].surname == "ПАЛВАНОВ"
    assert controller.printed["personal_number"] == "2600263521"


def test_run_refuses_before_anything_is_read(view) -> None:
    from PySide6.QtWidgets import QMessageBox

    screen, controller = _make(view, _passport())
    QMessageBox.information = staticmethod(lambda *a: None)
    screen._passport = _Drop(None)
    screen._run_ai()
    assert not controller.printed


def test_a_failed_read_opens_the_panel_for_typing(view) -> None:
    from src.common.errors import OfisError

    screen, _ = _make(view, _passport())
    screen._c.read_passport = lambda *a: (_ for _ in ()).throw(
        OfisError("AI жавоб бермади"))
    screen._passport = _Drop("p.jpg")
    screen._read_now()
    assert not screen._review.isHidden()


def test_the_one_shot_path_stays_for_screenless_callers() -> None:
    from src.controllers.beydjik_controller import BeydjikController

    assert hasattr(BeydjikController, "generate_from_image")
    assert hasattr(BeydjikController, "read_passport")
    assert hasattr(BeydjikController, "generate")


def test_patent_is_the_same_screen_with_the_review(view, monkeypatch) -> None:
    """ПАТЕНТ inherits БЕЙДЖИК, so it gets the panel for free."""
    import src.ui.views.patent_view as pv

    class _PatentCtl(_Controller):
        def blank_state(self, region):
            return "юкланмаган"

        def import_blank(self, *a):
            pass

    screen = pv.PatentView(_PatentCtl(_passport()))
    assert hasattr(screen, "_review")
    assert screen._review.isHidden()
