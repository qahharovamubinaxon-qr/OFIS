"""Learning a firm's «Уведомление» layout from its own blank."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import fitz
import pytest

from src.ai.base import AiRawResult
from src.common.errors import OfisError
from src.config import paths
from src.domain.enums import DocType
from src.services import uved_layout

ROOT = Path(__file__).resolve().parents[2]
BLANK = ROOT / "templates" / "trud_stroyinvest" / "uvedomlenie.pdf"
HAS_BLANK = BLANK.exists()

pytestmark = pytest.mark.skipif(
    not HAS_BLANK, reason="уведомление blank not bundled")


@pytest.fixture(autouse=True)
def _appdata(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


# The section headings of the bundled СТРОЙИНВЕСТ blank, as fractions of the
# page height — what the model is asked to read.
HEADINGS = {1: {"worker": 0.718},
            2: {"doc": 0.132, "patent": 0.42, "work": 0.72},
            3: {"mvd": 0.11}}


class _Headings:
    """Stands in for the vision model, which reads only the section headings."""

    def __init__(self, table: dict | None = None, *, drop: set[str] | None = None,
                 shift: float = 0.0) -> None:
        self._table = table if table is not None else HEADINGS
        self._drop = drop or set()
        self._shift = shift
        self.page = 0
        self.calls = 0

    def available(self) -> bool:
        return True

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        self.page += 1
        self.calls += 1
        answer = {k: v + self._shift
                  for k, v in self._table.get(self.page, {}).items()
                  if k not in self._drop}
        return AiRawResult(document_type=doc_type, fields=answer, provider="fake")


class _NoAi:
    def available(self) -> bool:
        return False

    def extract(self, *_a, **_k):  # pragma: no cover - never reached
        raise AssertionError("should not be called without a key")


# ------------------------------------------------------------------ ink


def test_the_forms_field_lines_are_found() -> None:
    doc = fitz.open(BLANK)
    try:
        rules = uved_layout.detect_rules(doc)
    finally:
        doc.close()
    assert len(rules) > 20, len(rules)
    # every page of this form carries field lines
    assert {r.page for r in rules} == {1, 2, 3}
    assert all(0 < r.y < 871 for r in rules)
    # the header divider runs the whole page width and must not be mistaken
    # for a field line
    assert all(r.value_x is None or 95 < r.value_x < 130 for r in rules)


def test_the_blanks_own_filled_rows_teach_the_house_style() -> None:
    """The employer block is already filled in — that is the worked example."""
    doc = fitz.open(BLANK)
    try:
        rules = uved_layout.detect_rules(doc)
    finally:
        doc.close()

    filled = [r for r in rules if r.filled]
    assert len(filled) >= 8, "the employer block should read as filled"
    x, gap, size = uved_layout.house_style(rules)
    assert 100 < x < 110, x            # the form's left column
    assert 2.0 < gap < 6.0, gap        # a value sits just above its line
    assert 8.0 <= size <= 12.0, size


def test_the_value_column_is_measured_page_by_page() -> None:
    """Госуслуги do not set every page to the same left margin.

    Writing them all at one x left half the form looking as though a space had
    been typed in front of each value, so each page keeps its own column.
    """
    doc = fitz.open(BLANK)
    try:
        rules = uved_layout.detect_rules(doc)
        column = uved_layout.value_column(rules, len(doc))
    finally:
        doc.close()

    assert set(column) == {1, 2, 3}
    for page, x in column.items():
        own = [r.value_x for r in rules if r.filled and r.page == page]
        if own:
            assert min(own) - 1.0 <= x <= max(own) + 1.0, (page, x, own)


def test_a_page_with_nothing_filled_borrows_the_documents_column() -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=871)
    page.insert_text((97, 300), "ОБЩЕСТВО", fontsize=10)
    page.draw_line((97, 304), (371, 304), width=0.7)
    doc.new_page(width=595, height=871)          # nothing on it at all
    rules = uved_layout.detect_rules(doc)
    column = uved_layout.value_column(rules, len(doc))
    doc.close()
    assert column[2] == column[1]


def test_a_pdf_with_no_filled_row_is_refused() -> None:
    """Without a worked example there is nothing to copy the style from."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=871)
    page.draw_line((102, 300), (371, 300), width=0.7)
    rules = uved_layout.detect_rules(doc)
    doc.close()
    with pytest.raises(OfisError):
        uved_layout.house_style(rules)


# ---------------------------------------------------------------- study


def test_a_blank_is_studied_into_a_usable_mapping() -> None:
    result = uved_layout.study(BLANK, _Headings())
    assert result.ok
    assert result.pages == 3

    ids = [f["id"] for f in result.fields]
    assert ids[:3] == ["uved.surname", "uved.name", "uved.patronymic"]
    assert len(set(ids)) == len(ids), "a field was mapped twice"

    for field in result.fields:
        assert field["type"] == "text"
        assert 1 <= field["page"] <= result.pages
        assert 20 < field["y"] < 871
        assert 100 < field["x"] < 110


def test_each_field_lands_on_its_own_line() -> None:
    """Two values on one line would print on top of each other."""
    result = uved_layout.study(BLANK, _Headings())
    spots = [(f["page"], round(f["y"], 1)) for f in result.fields]
    assert len(set(spots)) == len(spots), spots


def test_values_go_down_the_page_in_the_order_the_form_prints_them() -> None:
    result = uved_layout.study(BLANK, _Headings())
    spots = [(f["page"], f["y"]) for f in result.fields]
    assert spots == sorted(spots), spots


def test_a_section_the_model_did_not_find_is_reported_not_guessed() -> None:
    """Its fields stay blank — they are never shifted onto free lines.

    A missing heading also takes the section *above* it with it: that heading
    was where the previous section ended, so its line count no longer adds up.
    Refusing both is the safe reading, and the ones further down still land.
    """
    result = uved_layout.study(BLANK, _Headings(drop={"doc"}))
    ids = [f["id"] for f in result.fields]

    assert "uved.passport.series" not in ids      # the section that went missing
    assert "uved.surname" not in ids              # …and the one it bounded
    assert "uved.patent.series" in ids            # below it, unaffected
    assert "uved.contract_date" in ids
    assert any("Серия" in m for m in result.missing)
    assert any("Фамилия" in m for m in result.missing)


def test_a_heading_reported_a_little_off_is_still_understood() -> None:
    """The model only has to be roughly right about where a section starts."""
    exact = uved_layout.study(BLANK, _Headings())
    sloppy = uved_layout.study(BLANK, _Headings(shift=0.02))   # ~17pt low
    assert [f["id"] for f in sloppy.fields] == [f["id"] for f in exact.fields]
    assert not sloppy.missing


def test_a_line_the_firm_pre_filled_does_not_shift_the_rest() -> None:
    """This blank prints «Не заполнено» on a line that is ours to write on.

    Counting only the empty lines put every field after it one row out, so the
    whole printed sequence is counted instead.
    """
    result = uved_layout.study(BLANK, _Headings())
    assert len(result.fields) == len(uved_layout.FIELDS)
    assert not result.missing


def test_studying_without_an_ai_key_is_refused_clearly() -> None:
    with pytest.raises(OfisError) as exc:
        uved_layout.study(BLANK, _NoAi())
    assert "AI" in exc.value.message


def test_an_unreadable_file_is_refused() -> None:
    junk = Path(tempfile.mkdtemp()) / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(OfisError):
        uved_layout.study(junk, _Headings())


# ----------------------------------------------------------------- save


def test_the_mapping_is_saved_beside_the_firms_own_template(tmp_path) -> None:
    template = tmp_path / "uvedomlenie.pdf"
    template.write_bytes(BLANK.read_bytes())
    result = uved_layout.study(BLANK, _Headings())

    saved = uved_layout.save(result, template, tmp_path)
    assert saved == tmp_path / uved_layout.MAPPING_NAME
    assert uved_layout.mapping_for(template) == saved

    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["fields"] == result.fields
    assert data["page_size"][0] == pytest.approx(595.3, abs=1.0)


def test_a_firm_with_no_study_falls_back_to_the_bundled_mapping(tmp_path) -> None:
    template = tmp_path / "uvedomlenie.pdf"
    template.write_bytes(BLANK.read_bytes())
    assert uved_layout.mapping_for(template) is None


def test_the_saved_mapping_actually_fills_the_blank() -> None:
    """End to end: study the blank, fill it, read the values back out."""
    from src.pdf.engine import fill
    from src.pdf.mapping import FieldMapping

    folder = Path(tempfile.mkdtemp())
    template = folder / "uvedomlenie.pdf"
    template.write_bytes(BLANK.read_bytes())
    saved = uved_layout.save(
        uved_layout.study(BLANK, _Headings()), template, folder)

    out = folder / "filled.pdf"
    fill(template, FieldMapping.load(saved), {
        "uved.surname": "Назаров", "uved.name": "Муродулло",
        "uved.patronymic": "Хаиталиевич", "uved.birth_date": "22.02.2004",
        "uved.gender": "Мужской",
    }, out)

    text = " ".join(" ".join(p.get_text().split()) for p in fitz.open(out))
    for value in ("Назаров", "Муродулло", "Хаиталиевич", "22.02.2004", "Мужской"):
        assert value in text, value
