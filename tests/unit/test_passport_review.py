"""The shared «Ҳужжатлардан ўқилгани» panel — read, show, correct, hand back.

Every section that reads a passport now shows what was read in editable boxes
first, so a misread name is caught before it goes onto a filed document. That
panel lives in one place; this pins the behaviour every section leans on.
"""

from __future__ import annotations

from datetime import date

import pytest
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender
from src.ui.widgets.passport_review import PassportReview, _date_of, _date_text

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _passport() -> Passport:
    return Passport(
        surname="PALVANOV", name="DOVLETGELDI", number="046688", series="A2",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE,
        birth_date=date(1990, 5, 15), issue_date=date(2023, 3, 13),
        expiry_date=date(2028, 3, 12))


def _patent() -> Patent:
    return Patent(number="240", profession="рабочий",
                  holder_surname="ПАЛВАНОВ", holder_name="ДОВЛЕТГЕЛДИ",
                  holder_patronymic="БАЙРАМОВИЧ",
                  holder_citizenship="ТУРКМЕНИСТАН")


def test_it_starts_hidden() -> None:
    assert PassportReview().isHidden()


def test_fill_reveals_and_shows_the_passport() -> None:
    panel = PassportReview()
    panel.fill(_passport())
    assert not panel.isHidden()
    assert panel._boxes["surname"].text() == "PALVANOV"
    assert panel._boxes["citizenship"].text() == "ТУРКМЕНИСТАН"
    assert panel._boxes["number"].text() == "046688"


def test_the_patents_russian_name_wins() -> None:
    panel = PassportReview()
    panel.fill(_passport(), _patent())
    assert panel._boxes["surname"].text() == "ПАЛВАНОВ"          # patent, Russian
    assert panel._boxes["patronymic"].text() == "БАЙРАМОВИЧ"


def test_dates_and_gender_are_shown() -> None:
    panel = PassportReview()
    panel.fill(_passport())
    assert panel._boxes["issue_date"].text() == "13.03.2023"
    assert panel._gender.currentText() == "Мужской"
    assert panel._born.date().toString("dd.MM.yyyy") == "15.05.1990"


def test_edited_returns_what_is_in_the_boxes() -> None:
    panel = PassportReview()
    panel.fill(_passport(), _patent())
    panel._boxes["surname"].setText("ПАЛВАНОВА")        # operator fixes a misread
    worker = panel.edited()
    assert worker.surname == "ПАЛВАНОВА"
    assert worker.number == "046688"
    assert worker.nationality == "ТУРКМЕНИСТАН"
    assert worker.issue_date == date(2023, 3, 13)


def test_edited_keeps_fields_the_panel_never_shows() -> None:
    """issued_by (and the like) are not on the panel — a correction must not
    wipe them; they ride through untouched from the read passport."""
    passport = _passport()
    passport.issued_by = "МВД РОССИИ ПО Г. МОСКВЕ"
    passport.birth_place = "г. АШХАБАД"
    panel = PassportReview()
    panel.fill(passport)
    panel._boxes["surname"].setText("ПАЛВАНОВА")     # correct a misread
    worker = panel.edited()
    assert worker.surname == "ПАЛВАНОВА"              # correction applied
    assert worker.issued_by == "МВД РОССИИ ПО Г. МОСКВЕ"   # …and kept
    assert worker.birth_place == "г. АШХАБАД"


def test_edited_without_a_read_builds_a_fresh_passport() -> None:
    panel = PassportReview()
    panel.reveal()
    panel._boxes["surname"].setText("ИВАНОВ")
    panel._boxes["number"].setText("123")
    worker = panel.edited()
    assert worker.surname == "ИВАНОВ"
    assert worker.number == "123"


def test_edited_patent_syncs_the_name_and_keeps_its_details() -> None:
    panel = PassportReview()
    panel.fill(_passport(), _patent())
    panel._boxes["surname"].setText("ПАЛВАНОВА")      # operator fixes the name
    patent = panel.edited_patent()
    assert patent.holder_surname == "ПАЛВАНОВА"        # patent name follows
    assert patent.number == "240"                      # its own details stay


def test_edited_patent_is_none_without_a_patent() -> None:
    panel = PassportReview()
    panel.fill(_passport())
    assert panel.edited_patent() is None


def test_has_surname_tracks_the_box() -> None:
    panel = PassportReview()
    panel.fill(_passport())
    assert panel.has_surname()
    panel._boxes["surname"].clear()
    assert not panel.has_surname()


def test_reset_empties_and_hides() -> None:
    panel = PassportReview()
    panel.fill(_passport())
    panel.reset()
    assert panel.isHidden()
    assert panel._boxes["surname"].text() == ""


def test_reveal_opens_an_empty_panel_for_typing() -> None:
    panel = PassportReview()
    panel.reveal()
    assert not panel.isHidden()
    assert not panel.has_surname()


def test_a_custom_title_is_kept() -> None:
    assert PassportReview("Текшириш").title() == "Текшириш"


# -------------------------------------------------------- the date helpers
def test_date_text_formats_or_empties() -> None:
    assert _date_text(date(2025, 1, 18)) == "18.01.2025"
    assert _date_text(None) == ""


def test_date_of_reads_the_shapes_it_prints() -> None:
    assert _date_of("18.01.2025") == date(2025, 1, 18)
    assert _date_of("2025-01-18") == date(2025, 1, 18)
    assert _date_of("нет") is None
