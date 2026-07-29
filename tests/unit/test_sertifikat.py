"""СЕРТИФИКАТ — the rules the certificate is printed by."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import fitz
import pytest
from src.pdf.sertifikat_renderer import (
    SertifikatData,
    cyrillic_line,
    latin_line,
    render,
    roll_number,
    to_latin,
    valid_until,
)
from src.pdf.sertifikat_spec import BLANK_PAGE, ROLL_DIGITS, VALUE_PAGE
from src.services.sertifikat_service import SertifikatService

BLANK = Path("templates") / "sertifikat" / "standart"


def plain(text: str) -> str:
    """What the page says, with PyMuPDF's typographic spaces folded back.

    Extraction reports the spaces inside a drawn line as U+00A0 and a hyphen as
    U+00AD; the page itself carries ordinary ones. Folding them here keeps the
    assertions about *what is printed* rather than about how it reads back.
    """
    return text.replace("\xa0", " ").replace("\xad", "-")


# ------------------------------------------------------------------- dates
def test_three_years_less_a_day():
    """«10.07.2026 → 09.07.2029» — the office's own example."""
    assert valid_until(date(2026, 7, 10)) == date(2029, 7, 9)


def test_leap_day_does_not_crash():
    assert valid_until(date(2024, 2, 29)) == date(2027, 2, 28)


# ------------------------------------------------------------------- names
def test_the_two_lines_of_the_office_sample():
    """The certificate the office filled in: three names, then two in Latin."""
    assert cyrillic_line("Азизов", "Нусратулло", "Мейликович") == \
        "АЗИЗОВ НУСРАТУЛЛО МЕЙЛИКОВИЧ"
    assert latin_line("Азизов", "Нусратулло") == "AZIZOV NUSRATULLO"


def test_latin_line_drops_the_patronymic():
    """The passport's Latin line carries none, so neither does this one."""
    assert "MEILIKOVICH" not in latin_line("Азизов", "Нусратулло")


def test_tajik_letters_reach_latin():
    """A Tajik passport spells with letters Russian does not have."""
    assert to_latin("ҶУМАЕВ") == "JUMAEV"
    assert to_latin("РАҲИМОВ") == "RAKHIMOV"


def test_latin_input_survives():
    assert to_latin("AZIZOV") == "AZIZOV"


# ----------------------------------------------------------------- numbers
def test_only_the_last_three_figures_move():
    assert roll_number("002010264154", ROLL_DIGITS, "257") == "002010264257"
    assert roll_number("0142400796702", ROLL_DIGITS, "963") == "0142400796963"


def test_a_short_number_is_left_alone():
    assert roll_number("12", ROLL_DIGITS, "999") == "12"


def test_the_block_survives_the_roll():
    """Whatever the centre's block is, only its tail is ever re-rolled."""
    rolled = {SertifikatService.roll("002010264154") for _ in range(40)}
    assert all(value.startswith("002010264") for value in rolled)
    assert all(len(value) == 12 for value in rolled)
    assert len(rolled) > 1, "the tail must actually move"


# --------------------------------------------------------------- the sheet
@pytest.mark.skipif(not (BLANK / "page2.pdf").exists(),
                    reason="bundled certificate blank not present")
def test_the_pdf_is_two_pages_and_only_the_second_is_written_on():
    data = SertifikatData(
        surname="Азизов", name="Нусратулло", patronymic="Мейликович",
        city="Москва", issued_on=date(2026, 7, 1),
        reg_number="002010264154", barcode_number="0142400796702")
    doc = fitz.open("pdf", render(data, BLANK))
    assert doc.page_count == 2

    blank_text = doc[BLANK_PAGE].get_text().strip()
    assert blank_text == "", "page 1 must stay exactly as the paper is"

    written = plain(doc[VALUE_PAGE].get_text())
    for expected in ("АЗИЗОВ НУСРАТУЛЛО МЕЙЛИКОВИЧ", "AZIZOV NUSRATULLO",
                     "Москва", "002010264154", "01.07.2026", "30.06.2029"):
        assert expected in written, expected


@pytest.mark.skipif(not (BLANK / "page2.pdf").exists(),
                    reason="bundled certificate blank not present")
def test_the_barcode_figures_land_under_the_bars():
    """Thirteen figures, spread across the bars printed above them."""
    from src.pdf.sertifikat_spec import BARCODE_BARS

    data = SertifikatData(surname="Азизов", name="Нусратулло",
                          issued_on=date(2026, 7, 1),
                          barcode_number="0142400796702")
    doc = fitz.open("pdf", render(data, BLANK))
    digits = [span for block in doc[VALUE_PAGE].get_text("dict")["blocks"]
              for line in block.get("lines", [])
              for span in line["spans"]
              if span["bbox"][1] > BARCODE_BARS[3]
              and span["bbox"][3] < BARCODE_BARS[3] + 16
              and span["text"].strip().isdigit()]
    assert len(digits) == 13
    assert digits[0]["bbox"][0] >= BARCODE_BARS[0] - 1
    assert digits[-1]["bbox"][2] <= BARCODE_BARS[2] + 1


@pytest.mark.skipif(not (BLANK / "page2.pdf").exists(),
                    reason="bundled certificate blank not present")
def test_a_long_name_is_set_smaller_rather_than_cut():
    data = SertifikatData(
        surname="Абдурахманов-Хайдарбеков", name="Мухаммадамин",
        patronymic="Абдужаббарович", issued_on=date(2026, 7, 1))
    doc = fitz.open("pdf", render(data, BLANK))
    written = plain(doc[VALUE_PAGE].get_text())
    assert "АБДУРАХМАНОВ-ХАЙДАРБЕКОВ МУХАММАДАМИН АБДУЖАББАРОВИЧ" in written


# --------------------------------------------------------------- the service
def test_the_service_refuses_a_certificate_with_no_name(tmp_path):
    from src.common.errors import ValidationError

    with pytest.raises(ValidationError):
        SertifikatService().generate(surname="", name="",
                                     issued_on=date(2026, 7, 1))
