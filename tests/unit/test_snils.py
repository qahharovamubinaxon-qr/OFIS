"""СНИЛС — «Ишчининг СНИЛС номери»."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import fitz
import pytest
from src.common.errors import ValidationError
from src.pdf.snils_renderer import (
    SnilsData,
    form_date,
    format_snils,
    gender_word,
    render,
)
from src.pdf.snils_spec import DEFAULT_SNILS, SLOTS, VALUE_X
from src.services.snils_service import SnilsService

BLANK = Path("templates") / "snils" / "standart"


# -------------------------------------------------------------- formatting
def test_the_form_dates_itself_in_the_genitive():
    """«"25" июня 1997» — the day quoted, the month spelled out, «of June»."""
    assert form_date(date(1997, 6, 25)) == '"25" июня 1997'
    assert form_date(date(2026, 1, 6)) == '"06" января 2026'
    assert form_date(None) == ""


def test_the_number_takes_the_shape_the_form_prints():
    assert format_snils("22390231633") == "223-902-316 33"
    assert format_snils("223-902-316 33") == "223-902-316 33"


def test_a_number_that_is_not_eleven_digits_is_left_as_typed():
    """The operator may be copying something punctuated another way."""
    assert format_snils("123") == "123"
    assert format_snils("") == ""


def test_sex_reads_the_same_however_it_arrived():
    for said in ("female", "Ж", "женский", "F"):
        assert gender_word(said) == "ЖЕНСКИЙ"
    for said in ("male", "М", "Мужской", "m"):
        assert gender_word(said) == "МУЖСКОЙ"
    assert gender_word("") == ""


# ------------------------------------------------------------------ layout
def test_every_value_starts_in_the_same_column():
    """Measured off the office's sheet: they all line up but the number."""
    for key, slot in SLOTS.items():
        if key != "snils":
            assert slot.x == VALUE_X, f"{key} is out of the column"
    assert SLOTS["snils"].x > VALUE_X, "the number sits on its own label"


def test_the_baselines_go_down_the_page_in_order():
    order = ["snils", "surname", "name", "patronymic", "birth_date",
             "birth_place", "gender", "reg_date"]
    lines = [SLOTS[k].baseline for k in order]
    assert lines == sorted(lines), "the rows are out of order"


# ------------------------------------------------------------------- sheet
@pytest.mark.skipif(not (BLANK / "blank.pdf").exists(),
                    reason="bundled СНИЛС blank not present")
def test_the_sheet_carries_what_was_typed_and_not_what_was_there():
    """The bundled blank is a FILLED one, so the old values must be gone."""
    data = SnilsData(surname="Ибрагимов", name="Дилшод", patronymic="Акмалович",
                     birth_date=date(1990, 2, 1), birth_place="Узбекистан",
                     gender="male", reg_date=date(2026, 7, 30),
                     snils="11122233344")
    page = fitz.open("pdf", render(data, BLANK))[0]
    shot = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
    import numpy as np

    img = np.frombuffer(shot.samples, dtype="uint8").reshape(
        shot.height, shot.width, shot.n)[..., :3]
    # the value column, from the number down to the last row
    band = img[int(230 * 0.5):int(1140 * 0.5), int(780 * 0.5):int(1660 * 0.5)]
    assert band.mean() > 200, "the value column came out dark — a cover failed"


@pytest.mark.skipif(not (BLANK / "blank.pdf").exists(),
                    reason="bundled СНИЛС blank not present")
def test_the_sheet_is_one_page():
    data = SnilsData(surname="Ибрагимов", name="Дилшод",
                     reg_date=date(2026, 7, 30))
    assert fitz.open("pdf", render(data, BLANK)).page_count == 1


# ----------------------------------------------------------------- service
def test_a_sheet_with_no_name_is_refused():
    with pytest.raises(ValidationError):
        SnilsService().generate(surname="", name="", reg_date=date(2026, 7, 30))


def test_the_office_number_stands_in_the_box_until_it_is_changed():
    assert SnilsService().number() == DEFAULT_SNILS


def test_the_bundled_blank_cannot_be_deleted():
    """It ships with the program; deleting it leaves nothing to print on."""
    service = SnilsService()
    bundled = service.templates()[0]
    with pytest.raises(ValidationError):
        service.remove_template(bundled)
    assert bundled.exists()
