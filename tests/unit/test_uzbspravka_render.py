"""One worker's four certificates, drawn onto the office's own sheets."""

from __future__ import annotations

from datetime import date, datetime

import fitz
import pytest
from src.pdf.uzbspravka_renderer import (
    QR_KEY,
    UzbData,
    output_stem,
    placed,
    placed_images,
    render,
    values,
)
from src.pdf.uzbspravka_spec import PAGE_H, PAGE_W, SEAL_KEY


def _data(**over) -> UzbData:
    made = UzbData(
        surname="Эргашев", name="Умиджон", patronymic="Шухрат Угли",
        latin_name="ERGASHEV UMIDJON SHUKHRAT UGLI",
        birth_date=date(2002, 10, 2), passport="FA3445084",
        pinfl="50210025720042", firm="ООО СФЕРА",
        number_tail="9330-6055", code="1548", request_no="170387888",
        made_at=datetime(2026, 7, 28, 13, 3, 46))
    for key, value in over.items():
        setattr(made, key, value)
    return made


def _spans(pdf: bytes) -> dict[str, tuple[float, float]]:
    found = {}
    with fitz.open("pdf", pdf) as doc:
        for block in doc[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    text = " ".join(span["text"].split())
                    if text:
                        found[text] = (span["origin"][0] / PAGE_W,
                                       span["origin"][1] / PAGE_H)
    return found


@pytest.mark.parametrize("sheet", [1, 2, 3, 4])
def test_every_sheet_comes_out_a4_with_the_worker_on_it(sheet) -> None:
    made = render(_data(), sheet)
    with fitz.open("pdf", made) as doc:
        assert doc.page_count == 1
        assert doc[0].rect.width == pytest.approx(PAGE_W)
        assert doc[0].rect.height == pytest.approx(PAGE_H)
    printed = _spans(made)
    assert "50210025720042" in printed, "ПИНФЛ ёзилмади"
    assert "1548" in printed, "4 хонали код ёзилмади"
    assert "ERGASHEV UMIDJON SHUKHRAT UGLI" in printed
    assert "02.10.2002" in printed


def test_the_first_three_write_one_name_line_and_the_fourth_writes_three(
) -> None:
    on123 = _spans(render(_data(), 1))
    assert "ЭРГАШЕВ УМИДЖОН ШУХРАТ УГЛИ" in on123
    on4 = _spans(render(_data(), 4))
    assert "ЭРГАШЕВ" in on4 and "УМИДЖОН" in on4 and "ШУХРАТ УГЛИ" in on4
    assert "ЭРГАШЕВ УМИДЖОН ШУХРАТ УГЛИ" not in on4


def test_the_time_is_written_the_way_each_sheet_writes_it() -> None:
    """1–3 print the second, 4 prints the day and the hour."""
    assert values(_data(), 1)["issued_at"] == "2026-07-28 13:03:46"
    assert values(_data(), 4)["issued_at"] == "28.07.2026 13:03"
    assert values(_data(), 1)["created"] == "2026-07-28"


def test_a_worker_without_a_code_leaves_the_box_empty() -> None:
    printed = _spans(render(_data(code="", number_tail=""), 1))
    assert "1548" not in printed and "9330-6055" not in printed


def test_the_seal_and_the_qr_are_drawn_where_the_office_put_them() -> None:
    seal = _png()
    made = render(_data(seal_png=seal, qr_png=seal), 2)
    with fitz.open("pdf", made) as doc:
        assert len(doc[0].get_images(full=True)) == 2, "печать ёки QR тушмади"
    # and each sheet remembers its own places
    moved = {"images": {"2": {SEAL_KEY: [0.10, 0.30, 0.05]}}}
    where = placed_images(2, moved)
    assert where[SEAL_KEY] == (0.10, 0.30, 0.05)
    assert where[QR_KEY] == placed_images(1, {})[QR_KEY]


def test_a_dragged_value_moves_on_that_sheet_only() -> None:
    moved = {"fields": {"4": {"pinfl": [0.44, 0.62, 0.014]}}}
    assert placed(4, moved)["pinfl"].x == pytest.approx(0.44)
    assert placed(1, moved)["pinfl"].x != pytest.approx(0.44)


def test_the_file_is_named_by_the_worker_and_the_sheet() -> None:
    assert output_stem(_data(), 1) == "ЭРГАШЕВ_УМИДЖОН_1"
    assert output_stem(_data(), 4) == "ЭРГАШЕВ_УМИДЖОН_4"
    # a nameless worker must not produce a file called «3.pdf»
    assert output_stem(UzbData(), 3) == "SPRAVKA_3"


def _png() -> bytes:
    with fitz.open() as doc:
        page = doc.new_page(width=60, height=60)
        page.draw_circle(fitz.Point(30, 30), 22)
        return page.get_pixmap(dpi=72).tobytes("png")
