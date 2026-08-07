"""The № tail, and a blank that is named «.pdf» without being one.

Both came off the office's own screen: «Созлаш» died with «is no PDF» on
one of its four sheets, and the № came out eight digits where its own
paperwork carries sixteen.
"""

from __future__ import annotations

import re

import fitz
import pytest
from src.pdf.uzbspravka_renderer import UzbData, render
from src.services.uzbspravka_service import (
    TAIL_GROUPS,
    TAIL_KEPT,
    new_numbers,
    next_tail,
)

_SHAPE = re.compile(r"^\d{4}(-\d{4}){3}$")


def test_the_number_is_sixteen_digits_in_four_groups() -> None:
    """«3578-5254-8552-2705» — the office's own paperwork."""
    assert TAIL_GROUPS == 4 and TAIL_KEPT == 2
    assert _SHAPE.fullmatch(next_tail("3578-5254-8552-2705"))
    assert _SHAPE.fullmatch(next_tail(""))
    for made in new_numbers().values():
        assert _SHAPE.fullmatch(made.number_tail), made.number_tail


def test_the_office_s_own_front_stays_and_the_back_changes() -> None:
    """It fixed the first two groups once; the last two are the worker's."""
    saved = "3578-5254-8552-2705"
    made = [next_tail(saved) for _ in range(12)]
    assert all(m.startswith("3578-5254-") for m in made), "олди ўзгарган"
    backs = {m[10:] for m in made}
    assert len(backs) > 8, "охири ўзгармаяпти — ишчилар бир хил рақам олади"
    assert "8552-2705" not in backs or len(backs) > 1


@pytest.mark.parametrize("saved, front", [
    ("3578-5254-8552-2705", "3578-5254-"),
    ("3578 5254", "3578-5254-"),          # typed without dashes
    ("3578-5254", "3578-5254-"),          # only the part that is fixed
    ("1234", "1234-"),                    # filled in short
])
def test_whatever_the_office_typed_is_honoured_as_far_as_it_goes(saved, front
                                                                 ) -> None:
    made = next_tail(saved)
    assert made.startswith(front)
    assert _SHAPE.fullmatch(made)


def test_a_blank_named_pdf_that_is_not_one_still_prints(tmp_path) -> None:
    """One of the office's own four sheets was exactly this, and «📐
    Созлаш» stopped dead on it with «is no PDF»."""
    # a picture, saved under a «.pdf» name the way a phone scanner does
    pretender = tmp_path / "sheet3.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 60), "бланка")
        page.get_pixmap(dpi=72).pil_save(str(pretender), format="PDF")

    made = render(UzbData(surname="ЭРГАШЕВ", code="1548"), 3, pretender)
    with fitz.open("pdf", made) as doc:
        assert doc.page_count == 1
        assert "1548" in doc[0].get_text()
