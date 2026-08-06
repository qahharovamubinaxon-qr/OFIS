"""Where each value goes on the four Uzbek certificates.

The places were measured off the office's own sheets — it drew a blue rule
under everything that changes — so these tests hold the map to what was
measured rather than to anything invented.
"""

from __future__ import annotations

import pytest
from src.pdf.uzbspravka_spec import (
    PAGE_H,
    PAGE_W,
    SEAL_DEFAULT,
    SHEET4,
    SHEET123,
    SHEETS,
    slots_of,
)


def test_the_sheets_are_plain_a4() -> None:
    assert (PAGE_W, PAGE_H) == (595.0, 842.0)


def test_one_map_serves_the_first_three_certificates() -> None:
    """Their blue rules came back identical, so they are one sheet."""
    assert slots_of(1) is SHEET123
    assert slots_of(2) is SHEET123
    assert slots_of(3) is SHEET123
    assert slots_of(4) is SHEET4
    assert set(SHEETS) == {1, 2, 3, 4}
    # anything else falls back rather than crashing mid-print
    assert slots_of(9) is SHEET123


def test_every_certificate_names_the_worker_and_carries_the_code() -> None:
    for sheet, slots in SHEETS.items():
        for must in ("made_at", "number_tail", "latin_name", "created",
                     "request_no", "pinfl_top", "issued_at", "pinfl",
                     "birth_date", "code"):
            assert must in slots, f"{sheet}: {must}"


def test_the_first_three_write_the_name_on_one_line_and_the_fourth_on_three(
) -> None:
    """Certificate 4 lays the worker out down the page — фамилия, имя,
    отчество each on its own line — where the others print «Ф.И.О.»."""
    assert "fio" in SHEET123 and "surname" not in SHEET123
    assert {"surname", "name", "patronymic"} <= set(SHEET4)
    assert "fio" not in SHEET4


def test_the_code_is_the_biggest_thing_on_the_sheet() -> None:
    """The four digits at the foot are printed large, the way the office
    prints them — they are what a checker reads first."""
    for slots in (SHEET123, SHEET4):
        code = slots["code"]
        assert code.bold
        assert code.size > max(s.size for k, s in slots.items() if k != "code")


@pytest.mark.parametrize("sheet", [1, 2, 3, 4])
def test_nothing_is_placed_off_the_sheet(sheet) -> None:
    for key, slot in slots_of(sheet).items():
        assert 0.0 < slot.x < 1.0, f"{sheet}.{key} x"
        assert 0.0 < slot.baseline < 1.0, f"{sheet}.{key} baseline"
        assert 0.0 < slot.size < 0.06, f"{sheet}.{key} size"


def test_every_slot_has_a_label_and_a_sample() -> None:
    """«📐 Созлаш» shows a name and a preview for each, or the office
    cannot tell what it is dragging."""
    for sheet, slots in SHEETS.items():
        for key, slot in slots.items():
            assert slot.label, f"{sheet}.{key}"
            assert slot.sample, f"{sheet}.{key}"


def test_the_seal_starts_somewhere_on_the_sheet() -> None:
    left, bottom, height = SEAL_DEFAULT
    assert 0.0 < left < 1.0 and 0.0 < bottom <= 1.0
    assert 0.0 < height < 0.4
