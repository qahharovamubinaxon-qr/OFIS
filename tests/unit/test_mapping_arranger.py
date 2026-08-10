"""«📐 Созлаш» for the sections that print through a shared FieldMapping.

The office asked ХОСТЕЛ for what the newer sections already have: move a
value, resize it, pick its face, set it bold, add a text of its own. A
mapping is in POINTS and the editor works in FRACTIONS, so what is checked
here is the bridge between them — and, above all, that a text one office adds
to its own blank never reaches the mapping every office shares.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.engine import fill
from src.pdf.mapping import FieldMapping, own_values, with_layout
from src.ui.widgets.field_editor import OWN_TEXT
from src.ui.widgets.mapping_arranger import (
    label_of,
    sample_of,
    to_fields,
    to_layout,
)

PAGE = (595.28, 841.89)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


@pytest.fixture()
def mapping() -> FieldMapping:
    return FieldMapping(
        template="f.pdf", template_version="1", mapping_version="1",
        page_size=PAGE, fields=[
            {"id": "reg.surname", "type": "grid", "page": 1, "x0": 100.0,
             "y": 200.0, "size": 10.0, "pitch": 14.0, "font": "OfisSerif"},
            {"id": "reg.passport.issue.d", "type": "grid", "page": 1,
             "x0": 300.0, "y": 250.0, "size": 10.0, "pitch": 14.0},
            {"id": "reg.stay_from", "type": "text", "page": 2, "x": 80.0,
             "y": 400.0, "size": 9.5, "font": "OfisSerif"},
        ])


@pytest.fixture()
def blank(tmp_path) -> Path:
    made = tmp_path / "blank.pdf"
    doc = fitz.open()
    for _ in range(2):
        doc.new_page(width=PAGE[0], height=PAGE[1])
    doc.save(str(made))
    doc.close()
    return made


# --------------------------------------------------------------- the names
def test_a_field_id_is_turned_into_words_the_office_reads() -> None:
    """A mapping names its fields for the program. The office should not
    have to read «reg.passport.issue.d»."""
    assert label_of("reg.surname") == "Фамилия"
    assert label_of("reg.passport.series") == "Паспорт серия"
    assert "куни" in label_of("reg.passport.issue.d")
    assert label_of("reg.citizenship") == "Гражданство"


def test_a_name_the_section_gives_wins_over_the_guess() -> None:
    assert label_of("reg.surname", {"reg.surname": "ФАМИЛИЯСИ"}) == "ФАМИЛИЯСИ"


def test_an_unknown_id_is_shown_as_it_is_rather_than_hidden() -> None:
    assert label_of("something.odd") == "something odd"


def test_an_office_text_is_named_by_what_it_says() -> None:
    assert label_of(OWN_TEXT + "ИЗОҲ") == "✎ ИЗОҲ"
    assert sample_of(OWN_TEXT + "ИЗОҲ") == "ИЗОҲ"


# ------------------------------------------------------------ points in
def test_points_become_fractions_of_the_page(mapping) -> None:
    """The editor works in fractions so a blank re-scanned at another
    resolution still lands right."""
    fields, pitches = to_fields(mapping, None)
    first = next(f for f in fields if f.key == "reg.surname")
    assert first.x == pytest.approx(100.0 / PAGE[0])
    assert first.baseline == pytest.approx(200.0 / PAGE[1])
    assert first.size == pytest.approx(10.0 / PAGE[1])
    assert first.page == 1


def test_letter_cell_rows_keep_their_pitch(mapping) -> None:
    """A grid prints one glyph per printed box — drawn any other way, the
    office cannot line it up."""
    _fields, pitches = to_fields(mapping, None)
    assert pitches["reg.surname"] == pytest.approx(14.0 / PAGE[0])
    assert "reg.stay_from" not in pitches, "оддий матнга катак берилди"


def test_what_was_saved_before_comes_back_into_the_editor(mapping) -> None:
    kept = {"fields": {"reg.surname": {
        "x": 0.4, "y": 0.5, "size": 0.02, "font": "Arial",
        "bold": True, "colour": [0.9, 0.1, 0.1], "rotate": 90}}}
    fields, _ = to_fields(mapping, kept)
    first = next(f for f in fields if f.key == "reg.surname")
    assert first.font == "Arial" and first.bold is True
    assert first.colour == pytest.approx((0.9, 0.1, 0.1))
    assert first.rotate == 90


# ----------------------------------------------------------- fractions out
def test_the_editor_result_is_kept_as_position_and_style(mapping) -> None:
    from dataclasses import replace

    fields, _ = to_fields(mapping, None)
    moved = [replace(f, x=0.33, baseline=0.44, bold=True, font="Arial",
                     colour=(0.2, 0.3, 0.4)) if f.key == "reg.surname" else f
             for f in fields]
    made = to_layout(moved)
    body = made["fields"]["reg.surname"]
    assert body["x"] == pytest.approx(0.33)
    assert body["y"] == pytest.approx(0.44)
    assert body["bold"] is True and body["font"] == "Arial"
    assert body["colour"] == pytest.approx([0.2, 0.3, 0.4])
    assert made["texts"] == []


def test_a_text_the_office_added_is_kept_apart_from_the_form_fields(
        mapping) -> None:
    """It belongs to THIS blank, never to the mapping every office shares."""
    from dataclasses import replace

    fields, _ = to_fields(mapping, None)
    fields.append(replace(fields[0], key=OWN_TEXT + "ИЗОҲ", page=2,
                          x=0.2, baseline=0.9))
    made = to_layout(fields)

    assert list(made["fields"]) == ["reg.surname", "reg.passport.issue.d",
                                    "reg.stay_from"]
    assert len(made["texts"]) == 1
    assert made["texts"][0]["text"] == "ИЗОҲ"
    assert made["texts"][0]["page"] == 2


def test_an_office_text_survives_the_whole_round_trip(mapping) -> None:
    from dataclasses import replace

    fields, _ = to_fields(mapping, None)
    fields.append(replace(fields[0], key=OWN_TEXT + "ИЗОҲ", page=2,
                          x=0.2, baseline=0.9, bold=True))
    once = to_layout(fields)
    again, _ = to_fields(mapping, once)
    mine = [f for f in again if f.key.startswith(OWN_TEXT)]
    assert len(mine) == 1
    assert mine[0].key == OWN_TEXT + "ИЗОҲ"
    assert mine[0].page == 2 and mine[0].bold is True
    assert to_layout(again)["texts"] == once["texts"]


# ------------------------------------------------------------ and it prints
def test_the_arranged_blank_prints_what_the_office_chose(mapping,
                                                         blank) -> None:
    layout = {
        "fields": {"reg.stay_from": {"x": 0.2, "y": 0.3, "size": 0.02,
                                     "font": "Arial", "bold": True,
                                     "colour": [0.8, 0.0, 0.0]}},
        "texts": [{"text": "ЎЗ МАТНИМ", "page": 1, "x": 0.15, "y": 0.2,
                   "size": 0.018, "font": "Arial", "bold": False,
                   "colour": [0.0, 0.0, 0.6]}]}
    ready = with_layout(mapping, layout)
    values = {"reg.stay_from": "01.01.2026", **own_values(layout)}
    out = fill(blank, ready, values, blank.parent / "out.pdf",
               only_calibrated=False)

    with fitz.open(out) as doc:
        # PyMuPDF hands some faces back with non-breaking spaces in them, so
        # the words are compared with their whitespace evened out
        spans = {" ".join(s["text"].split()): s
                 for page in doc for bl in page.get_text("dict")["blocks"]
                 for ln in bl.get("lines", []) for s in ln["spans"]}
    assert "01.01.2026" in spans, "форманинг ўз қиймати чиқмади"
    assert "ЎЗ МАТНИМ" in spans, "офиснинг ўз матни чиқмади"
    assert "Bold" in spans["01.01.2026"]["font"], "қалин қилинмади"
    assert spans["01.01.2026"]["color"] == 0xCC0000
    assert spans["ЎЗ МАТНИМ"]["color"] == 0x000099


def test_a_blank_nobody_arranged_prints_exactly_as_before(mapping) -> None:
    """The office has forty-odd blanks already lined up — none may move."""
    for empty in (None, {}, {"fields": {}}, {"fields": {}, "texts": []}):
        same = with_layout(mapping, empty)
        assert [f.model_dump() for f in same.fields] == \
               [f.model_dump() for f in mapping.fields]


def test_the_three_number_shape_saved_years_ago_still_lands(mapping) -> None:
    """Every existing blank holds ``[x, y, size]`` and must keep working."""
    old = with_layout(mapping, {"fields": {"reg.surname": [0.25, 0.35, 0.02]}})
    first = next(f for f in old.fields if f.id == "reg.surname")
    assert first.x0 == pytest.approx(0.25 * PAGE[0])
    assert first.y == pytest.approx(0.35 * PAGE[1])
    assert first.size == pytest.approx(0.02 * PAGE[1])
