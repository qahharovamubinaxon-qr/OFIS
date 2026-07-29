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
    title_case,
    to_latin,
)
from src.pdf.ppu_spec import ADDRESS_LINES, BACK, FRONT, PHOTO_BOX, PHOTO_OPACITY
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


def test_an_address_goes_three_words_to_a_line():
    """The office writes them that way: three, three, and the rest."""
    lines = address_lines("г. Москва, 15-я Парковая, д. 33, ком. 2")
    assert lines == ["г. Москва, 15-я", "Парковая, д. 33,", "ком. 2"]


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
