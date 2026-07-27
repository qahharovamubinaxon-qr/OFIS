"""Learning where a PDF трудовой договор leaves room for the worker."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest

from src.ai.base import AiRawResult
from src.common.errors import OfisError
from src.config import paths
from src.domain.enums import DocType
from src.services import trud_layout

CONTRACT_HEIGHT = 822.0


@pytest.fixture(autouse=True)
def _appdata(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _contract(tmp_path: Path, *, requisites: int = 6, date_runs: int = 3) -> Path:
    """A stand-in built to the same shape as the firm's own contract.

    Underscore gaps on page 1, the six requisite lines and the signature table
    on the last page — including its full-height borders and a blue stamp, both
    of which the reader has to see past.
    """
    doc = fitz.open()
    first = doc.new_page(width=595, height=CONTRACT_HEIGHT)
    first.insert_text((60, 110), "г. Москва", fontsize=12)
    first.insert_text((410, 110), '«', fontsize=12)
    for i, (x0, x1) in enumerate([(413, 432), (441, 493), (500, 526)][:date_runs]):
        first.draw_line((x0, 112), (x1, 112), width=1.0)
    first.insert_text((60, 172), "…, и", fontsize=12)
    first.draw_line((365, 174), (540, 174), width=1.0)
    first.insert_text((60, 272), "1.1. …по должности", fontsize=12)
    first.draw_line((423, 274), (501, 274), width=1.0)

    doc.new_page(width=595, height=CONTRACT_HEIGHT)          # a body page

    last = doc.new_page(width=595, height=CONTRACT_HEIGHT)
    labels = ["Работник Ф.И.О.:", "Документ, удостоверяющий личность:",
              "паспорт серия номер:", "выдан:",
              "Патент … серия номер:", "выдан:"][:requisites]
    for i, label in enumerate(labels):
        last.insert_text((83, 358 + i * 16), label, fontsize=11)
    # the signature table: full-height borders, and the firm's blue stamp
    last.draw_rect(fitz.Rect(110, 491, 772 / 2 + 275, 603), width=1.0)
    last.draw_line((418, 491), (418, 603), width=1.0)
    last.insert_text((150, 545), "Работодатель", fontsize=11,
                     color=(0.1, 0.1, 0.7))
    last.draw_circle((150, 560), 30, width=3.0, color=(0.1, 0.1, 0.7))
    last.draw_line((304, 533), (407, 533), width=1.0)        # signature
    last.draw_line((410, 533), (502, 533), width=1.0)        # (name.)
    last.insert_text((304, 583), "Экземпляр получен и подписан", fontsize=11)
    for x0, x1 in ((307, 327), (336, 389), (392, 431)):
        last.draw_line((x0, 588), (x1, 588), width=1.0)

    path = tmp_path / "trudovoy.pdf"
    doc.save(str(path))
    doc.close()
    return path


ANCHORS = {1: {"contract_date": 111.0 / CONTRACT_HEIGHT,
               "worker_fio": 173.0 / CONTRACT_HEIGHT,
               "position": 273.0 / CONTRACT_HEIGHT},
           3: {"requisites": 356.0 / CONTRACT_HEIGHT,
               "sign_fio": 532.0 / CONTRACT_HEIGHT,
               "sign_date": 588.0 / CONTRACT_HEIGHT}}


class _Anchors:
    """Stands in for the vision model, which reads only where each place is."""

    def __init__(self, table: dict | None = None, *,
                 drop: set[str] | None = None) -> None:
        self._table = table if table is not None else ANCHORS
        self._drop = drop or set()
        self.page = 0

    def available(self) -> bool:
        return True

    def extract(self, image: bytes, doc_type: DocType, prompt: str) -> AiRawResult:
        self.page += 1
        answer = {k: v for k, v in self._table.get(self.page, {}).items()
                  if k not in self._drop}
        return AiRawResult(document_type=doc_type, fields=answer, provider="fake")


class _NoAi:
    def available(self) -> bool:
        return False

    def extract(self, *_a, **_k):  # pragma: no cover - never reached
        raise AssertionError("should not be called without a key")


# ------------------------------------------------------------------- ink


def test_the_gaps_left_for_the_worker_are_found(tmp_path) -> None:
    doc = fitz.open(_contract(tmp_path))
    try:
        lines = trud_layout.read_lines(doc)
    finally:
        doc.close()

    date_line = next(ln for ln in lines
                     if ln.page == 1 and ln.top < 115 and ln.runs)
    assert len(date_line.runs) == 3, date_line.runs
    fio_line = next(ln for ln in lines
                    if ln.page == 1 and 160 < ln.top < 180 and ln.runs)
    assert len(fio_line.runs) == 1


def test_the_stamp_is_not_mistaken_for_a_gap(tmp_path) -> None:
    """The last page carries a blue stamp whose strokes look like underscores."""
    doc = fitz.open(_contract(tmp_path))
    try:
        lines = trud_layout.read_lines(doc)
    finally:
        doc.close()

    stamp_rows = [ln for ln in lines if ln.page == 3 and 545 < ln.top < 580]
    assert all(not ln.runs for ln in stamp_rows), stamp_rows


def test_the_table_borders_do_not_weld_its_rows_together(tmp_path) -> None:
    """Full-height borders once made the whole table read as one line."""
    doc = fitz.open(_contract(tmp_path))
    try:
        lines = trud_layout.read_lines(doc)
    finally:
        doc.close()

    inside = [ln for ln in lines if ln.page == 3 and 491 <= ln.top <= 603]
    assert len(inside) > 2, inside
    assert all(ln.bottom - ln.top < 40 for ln in inside)


# ----------------------------------------------------------------- study


def test_a_contract_is_studied_into_a_usable_mapping(tmp_path) -> None:
    result = trud_layout.study(_contract(tmp_path), _Anchors())
    assert result.ok
    assert not result.missing

    ids = [f["id"] for f in result.fields]
    for expected in ("trud.contract_date_day", "trud.contract_date_month",
                     "trud.contract_date_year", "trud.worker_fio",
                     "trud.position", "trud.req_fio", "trud.req_patent_issued",
                     "trud.sign_fio", "trud.sign_date_year"):
        assert expected in ids, expected
    assert len(set(ids)) == len(ids), "a gap was used twice"


def test_the_requisites_keep_the_order_the_contract_prints_them(tmp_path):
    """«выдан:» appears twice, so the block is read as one run of six lines."""
    result = trud_layout.study(_contract(tmp_path), _Anchors())
    block = [f for f in result.fields if f["id"].startswith("trud.req_")]
    assert [f["id"] for f in block] == [i for i, _l in trud_layout.REQUISITES]
    assert [f["y"] for f in block] == sorted(f["y"] for f in block)


def test_a_value_starts_after_the_colon_not_on_top_of_it(tmp_path) -> None:
    result = trud_layout.study(_contract(tmp_path), _Anchors())
    doc = fitz.open(_contract(tmp_path))
    try:
        lines = trud_layout.read_lines(doc)
    finally:
        doc.close()

    field = next(f for f in result.fields if f["id"] == "trud.req_fio")
    label = next(ln for ln in lines if ln.page == 3 and 350 < ln.top < 362)
    assert field["x"] > label.x1, (field["x"], label.x1)
    assert field["x"] - label.x1 < 10.0


def test_a_place_the_model_did_not_find_is_reported_not_guessed(tmp_path):
    result = trud_layout.study(_contract(tmp_path), _Anchors(drop={"position"}))
    assert "trud.position" not in [f["id"] for f in result.fields]
    assert "position" in result.missing
    # the rest is still placed
    assert "trud.worker_fio" in [f["id"] for f in result.fields]


def test_a_date_line_that_is_not_three_gaps_is_left_alone(tmp_path) -> None:
    """Better blank than a year written where the month belongs."""
    result = trud_layout.study(_contract(tmp_path, date_runs=2), _Anchors())
    assert not [f for f in result.fields if "contract_date" in f["id"]]
    assert "contract_date" in result.missing


def test_a_requisites_block_of_the_wrong_length_is_left_alone(tmp_path) -> None:
    result = trud_layout.study(_contract(tmp_path, requisites=4), _Anchors())
    assert not [f for f in result.fields if f["id"].startswith("trud.req_")]
    assert "requisites" in result.missing


def test_studying_without_an_ai_key_is_refused_clearly(tmp_path) -> None:
    with pytest.raises(OfisError) as exc:
        trud_layout.study(_contract(tmp_path), _NoAi())
    assert "AI" in exc.value.message


def test_an_unreadable_file_is_refused(tmp_path) -> None:
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"not a pdf")
    with pytest.raises(OfisError):
        trud_layout.study(junk, _Anchors())


# ------------------------------------------------------------ end to end


def test_the_saved_mapping_fills_the_contract(tmp_path) -> None:
    from src.pdf.engine import fill
    from src.pdf.mapping import FieldMapping

    template = _contract(tmp_path)
    saved = trud_layout.save(
        trud_layout.study(template, _Anchors()), template, tmp_path)
    assert trud_layout.mapping_for(template) == saved

    out = tmp_path / "filled.pdf"
    fill(template, FieldMapping.load(saved), {
        "trud.contract_date_day": "28", "trud.contract_date_month": "июля",
        "trud.contract_date_year": "2026",
        "trud.worker_fio": "Назаров Муродулло",
        "trud.position": "Подсобный рабочий",
        "trud.req_fio": "Назаров Муродулло Хаиталиевич",
        "trud.sign_fio": "Назаров М. Х.",
    }, out)

    text = " ".join(" ".join(p.get_text().split()) for p in fitz.open(out))
    for value in ("28", "июля", "2026", "Назаров Муродулло",
                  "Подсобный рабочий", "Назаров М. Х."):
        assert value in text, value


def test_a_firm_with_no_study_falls_back_to_the_older_editor(tmp_path) -> None:
    assert trud_layout.mapping_for(_contract(tmp_path)) is None


def test_the_values_cover_every_gap_the_contract_leaves(tmp_path) -> None:
    """Whatever the study finds, the service must have something to put there."""
    from src.domain.documents import Passport, Patent
    from src.services.trud_service import TrudService

    result = trud_layout.study(_contract(tmp_path), _Anchors())
    values = TrudService._trud_values(
        Passport(surname="НАЗАРОВ", name="МУРОДУЛЛО",
                 patronymic="ХАИТАЛИЕВИЧ", number="5442519", series="FA",
                 issue_date=date(2023, 2, 16), issued_by="МВД РУз"),
        Patent(series="77", number="2600017664", issue_date=date(2026, 4, 14),
               issued_by="ГУ МВД России по г. Москве",
               profession="Подсобный рабочий"),
        form_date=date(2026, 7, 28), profession="Подсобный рабочий")

    for field in result.fields:
        assert field["id"] in values, field["id"]
        assert values[field["id"]], f"{field['id']} is empty"
