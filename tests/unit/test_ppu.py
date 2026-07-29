"""ППУ — the pair the office prints from a worker's регистрация."""

from __future__ import annotations

from datetime import date

import pytest
from src.common.errors import ValidationError
from src.pdf.ppu_renderer import (
    PpuData,
    address_lines,
    full_name,
    passport_line,
    tidy_address,
    title_case,
    to_latin,
)
from src.pdf.ppu_spec import (
    ADDRESS_LINES,
    ADDRESS_MAX_WORDS,
    ADDRESS_MIN_WORDS,
    ADDRESS_SHIFT,
    BACK,
    FRONT,
    PHOTO_BOX,
    PHOTO_OPACITY,
    TEXT_OPACITY,
)
from src.services.ppu_service import PpuService


# ------------------------------------------------------------------- names
def test_the_office_sample_reads_back():
    """Their own filled pair: «Арутюнян Артак Пайлунович»."""
    cyrillic = full_name("АРУТЮНЯН", "АРТАК", "ПАЙЛУНОВИЧ")
    assert cyrillic == "Арутюнян Артак Пайлунович"
    assert to_latin(cyrillic) == "Arutiunian Artak Pailunovich"


def test_no_capital_lands_in_the_middle_of_a_word():
    """«ю» inside a name is «iu» — a stray capital is what gets noticed."""
    latin = to_latin("Арутюнян")
    assert latin == "Arutiunian"
    assert latin[1:].islower() or "-" in latin


def test_a_hyphenated_surname_keeps_both_capitals():
    assert title_case("АБДУЛЛА-ЗОДА") == "Абдулла-Зода"


def test_a_name_already_in_latin_is_left_alone():
    assert to_latin("Artak") == "Artak"


# ------------------------------------------------------------------ layout
def test_every_value_sits_inside_the_page():
    """Fractions, so they must all be between 0 and 1 or they land off-sheet."""
    for name, slots in (("front", FRONT), ("back", BACK)):
        for key, slot in slots.items():
            assert 0.0 < slot.x < 1.0, f"{name}.{key} x={slot.x}"
            assert 0.0 < slot.baseline < 1.0, f"{name}.{key} y={slot.baseline}"
            assert 0.0 < slot.size < 0.1, f"{name}.{key} size={slot.size}"


def test_the_photo_window_is_a_real_box():
    left, top, right, bottom = PHOTO_BOX
    assert 0.0 < left < right < 1.0
    assert 0.0 < top < bottom < 1.0


def test_the_photograph_is_laid_on_at_seven_parts_in_ten():
    assert pytest.approx(0.70) == PHOTO_OPACITY


def test_the_passport_is_printed_five_times():
    """Against every «Иностранный паспорт» label: once in front, four behind.

    The back is torn into four parts and filed separately, so each part has to
    carry the passport or it cannot be matched back to the worker.
    """
    behind = [k for k in BACK if k.startswith("passport")]
    assert len(behind) == 4
    assert "passport" in FRONT


def test_the_passport_is_written_the_way_the_sheet_prints_it():
    """«FA 1234567» → «№FA1234567» — run together, behind a №."""
    assert passport_line("FA 1234567") == "№FA1234567"
    assert passport_line("AL0531591") == "№AL0531591"
    assert passport_line("") == ""
    assert passport_line("   ") == ""


# ----------------------------------------------------------------- service
def test_a_pair_with_no_name_is_refused():
    with pytest.raises(ValidationError):
        PpuService().generate(surname="", name="", valid_from=date(2026, 1, 14))


def test_printing_without_a_blank_says_so_plainly():
    """The office uploads its own blank; until then there is nothing to fill."""
    with pytest.raises(ValidationError) as caught:
        PpuService().generate(surname="Арутюнян", name="Артак",
                              valid_from=date(2026, 1, 14), template=None)
    assert "бланка" in str(caught.value).lower()


def test_the_data_carries_everything_the_pair_prints():
    data = PpuData(surname="Арутюнян", name="Артак", patronymic="Пайлунович",
                   birth_date=date(1977, 3, 3), gender="Мужской",
                   citizenship="АРМЕНИЯ", document="AL0531591",
                   address="г. Москва, 15-я Парковая, д. 33, ком. 2",
                   valid_from=date(2026, 1, 14), valid_to=date(2026, 4, 13))
    assert data.valid_to > data.valid_from
    assert data.address


# ----------------------------------------------------------------- address
def test_the_whole_address_is_kept_never_just_the_house():
    """«д. 33» alone is not an address — the reader is told so, in terms."""
    from src.ai.prompts import registration_prompt

    prompt = registration_prompt()
    for part in ("ОБЛАСТЬ", "РАЙОН", "ГОРОД", "УЛИЦА", "ДОМ", "КОРПУС",
                 "СТРОЕНИЕ", "КВАРТИРА"):
        assert part in prompt, f"the reader is not asked for {part}"
    assert "д. 33" in prompt, "it must be shown what a useless answer looks like"


def test_a_line_takes_four_long_words_or_five_short_ones():
    """Filled by WIDTH, not by count — that is what the office asked for."""
    short = address_lines("г. Москва, ул. Мира, д. 5, кв. 1")
    assert ADDRESS_MIN_WORDS <= len(short[0].split()) <= ADDRESS_MAX_WORDS
    long = address_lines("Московская обл., Балашихинский р-н, г. Балашиха, "
                         "ул. Ленина, д. 33")
    assert len(long[0].split()) == ADDRESS_MIN_WORDS, "long words crowd the line"


def test_a_line_never_ends_on_a_bare_abbreviation():
    """«…, д.» with «46» on the next line reads as two different things."""
    for text in ("г. Москва, ул. Домодедовская, д. 46, кв. 6",
                 "г. Москва, ул. Тульская, д. 2, кв. 15"):
        for line in address_lines(text):
            tail = line.rstrip(",")
            assert not tail.endswith(("д.", "кв.", "ул.", "корп.")), line


def test_a_street_run_into_its_abbreviation_is_put_right():
    """«улДомодедовская» names a street nobody can find."""
    assert tidy_address("г. Москва, улДомодедовская, д.46, кв.6") ==         "г. Москва, ул. Домодедовская, д. 46, кв. 6"
    assert tidy_address("ул.Домодедовская") == "ул. Домодедовская"


def test_an_ordinary_word_is_not_split_by_the_tidier():
    """«Тульская» begins with «ул» and must survive untouched."""
    assert tidy_address("ул. Тульская, д. 2") == "ул. Тульская, д. 2"
    assert tidy_address("г. Москва, ул. 8 Марта") == "г. Москва, ул. 8 Марта"


def test_the_type_is_laid_on_at_nine_parts_in_ten():
    assert pytest.approx(0.90) == TEXT_OPACITY


def test_the_address_block_sits_on_the_dates_line_a_centimetre_over():
    """Centred on «с … по …», and moved right by a centimetre."""
    assert BACK["address"].baseline == BACK["date_from"].baseline
    assert BACK["address"].x > BACK["date_to"].x
    assert pytest.approx(28.35 / 595.28) == ADDRESS_SHIFT


def test_a_long_address_keeps_its_tail_on_the_last_line():
    """Never dropped: an address without its flat number is not the address."""
    full = ("Московская обл., Балашихинский р-н, г. Балашиха, "
            "ул. Ленина, д. 33, корп. 2, стр. 1, кв. 15")
    lines = address_lines(full)
    assert len(lines) == ADDRESS_LINES
    assert "кв. 15" in lines[-1]
    assert " ".join(lines).split() == full.split(), "a word went missing"


def test_a_short_address_stays_on_one_line():
    assert address_lines("д. 33") == ["д. 33"]


def test_no_address_writes_nothing():
    assert address_lines("") == []
    assert address_lines("   ") == []
