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


class _Labels:
    """Stands in for the vision model.

    The real one reads the grey labels off the page; here the answer is built
    from the blank's own empty lines, so the snapping, validation and mapping
    output can be exercised without a key.
    """

    def __init__(self, path: Path, *, skip: set[str] | None = None,
                 collide: bool = False) -> None:
        doc = fitz.open(path)
        self._rules = uved_layout.detect_rules(doc)
        self._heights = [p.rect.height for p in doc]
        doc.close()
        self._skip = skip or set()
        self._collide = collide
        self.page = 0
        self.calls = 0

    def available(self) -> bool:
        return True

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        self.page += 1
        self.calls += 1
        height = self._heights[self.page - 1]
        empty = [r for r in self._rules if not r.filled]
        answer: dict[str, str] = {}
        for (key, _id, _label, _section), rule in zip(
                uved_layout.FIELDS, empty, strict=False):
            if key in self._skip or rule.page != self.page:
                continue
            answer[key] = round((rule.y - 20) / height, 4)
        if self._collide and answer:
            # two labels pointing at the same line — a model mistake
            first = next(iter(answer))
            for key in list(answer)[1:2]:
                answer[key] = answer[first]
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
    result = uved_layout.study(BLANK, _Labels(BLANK))
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
    result = uved_layout.study(BLANK, _Labels(BLANK))
    spots = [(f["page"], round(f["y"], 1)) for f in result.fields]
    assert len(set(spots)) == len(spots), spots


def test_values_go_down_the_page_in_the_order_the_form_prints_them() -> None:
    result = uved_layout.study(BLANK, _Labels(BLANK))
    spots = [(f["page"], f["y"]) for f in result.fields]
    assert spots == sorted(spots), spots


def test_a_label_the_model_could_not_find_is_reported_not_guessed() -> None:
    """A missing field is left blank on the form — never put on a free line."""
    result = uved_layout.study(BLANK, _Labels(BLANK, skip={"gender"}))
    assert "uved.gender" not in [f["id"] for f in result.fields]
    assert any("Пол" in m for m in result.missing)


def test_two_labels_on_one_line_drop_the_second_rather_than_overprint() -> None:
    result = uved_layout.study(BLANK, _Labels(BLANK, collide=True))
    spots = [(f["page"], round(f["y"], 1)) for f in result.fields]
    assert len(set(spots)) == len(spots)
    assert result.missing


def test_too_few_fields_is_not_treated_as_a_good_study() -> None:
    skip = {key for key, _id, _l, _s in uved_layout.FIELDS[:8]}
    result = uved_layout.study(BLANK, _Labels(BLANK, skip=skip))
    assert not result.ok
    assert len(result.missing) >= 8


def test_studying_without_an_ai_key_is_refused_clearly() -> None:
    with pytest.raises(OfisError) as exc:
        uved_layout.study(BLANK, _NoAi())
    assert "AI" in exc.value.message


def test_an_unreadable_file_is_refused() -> None:
    junk = Path(tempfile.mkdtemp()) / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(OfisError):
        uved_layout.study(junk, _Labels(BLANK))


# ----------------------------------------------------------------- save


def test_the_mapping_is_saved_beside_the_firms_own_template(tmp_path) -> None:
    template = tmp_path / "uvedomlenie.pdf"
    template.write_bytes(BLANK.read_bytes())
    result = uved_layout.study(BLANK, _Labels(BLANK))

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
        uved_layout.study(BLANK, _Labels(BLANK)), template, folder)

    out = folder / "filled.pdf"
    fill(template, FieldMapping.load(saved), {
        "uved.surname": "Назаров", "uved.name": "Муродулло",
        "uved.patronymic": "Хаиталиевич", "uved.birth_date": "22.02.2004",
        "uved.gender": "Мужской",
    }, out)

    text = " ".join(" ".join(p.get_text().split()) for p in fitz.open(out))
    for value in ("Назаров", "Муродулло", "Хаиталиевич", "22.02.2004", "Мужской"):
        assert value in text, value
