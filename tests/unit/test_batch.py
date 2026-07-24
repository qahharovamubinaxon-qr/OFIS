"""Bulk ZIP mode: classify images + generate one PDF per worker folder."""

from __future__ import annotations

import tempfile
import zipfile
from datetime import date
from pathlib import Path

import pytest

from src.ai.fake_provider import FakeProvider
from src.ai.manager import AiManager
from src.domain.enums import DocType
from src.ocr.service import OcrService
from src.services.batch_service import BatchService, classify_images

ROOT = Path(__file__).resolve().parents[2]
HAS_TEMPLATE = (ROOT / "templates" / "mvd_prilozhenie_7" / "template.pdf").exists()


def test_classify_named_and_positional() -> None:
    named = classify_images([Path("pasport.jpg"), Path("patent_old.png"), Path("patent_orqa.png")])
    assert named["passport"].name == "pasport.jpg"
    assert named["patent_back"].name == "patent_orqa.png"

    positional = classify_images([Path("a.jpg"), Path("b.jpg")])
    assert positional["passport"].name == "a.jpg"
    assert positional["patent"].name == "b.jpg"
    assert positional["patent_back"] is None


@pytest.mark.skipif(not HAS_TEMPLATE, reason="template missing")
def test_process_zip_generates_one_pdf_per_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    home = tempfile.mkdtemp()
    monkeypatch.setenv("HOME", home)
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    (Path(home) / "Desktop").mkdir()
    from src.config import paths

    paths.data_dir.cache_clear()
    from src.app import build_container
    from src.services.company_service import CompanyService
    from src.services.generation_service import GenerationService

    zip_path = Path(tempfile.mkdtemp()) / "workers.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for w in ("w1", "w2"):
            zf.writestr(f"{w}/pasport.jpg", b"IMG")
            zf.writestr(f"{w}/patent.jpg", b"IMG")

    c = build_container()
    canned = {
        DocType.PASSPORT: {"surname": "KARIMOV", "name": "AKMAL", "number": "1",
                           "nationality": "UZBEKISTAN", "birth_date": "1990-01-01"},
        DocType.PATENT: {"series": "50", "number": "9", "profession": "ПОДСОБНЫЙ РАБОЧИЙ",
                         "issue_date": "2026-05-10"},
    }
    ocr = OcrService(AiManager([FakeProvider(canned)]))
    batch = BatchService(ocr, c.resolve(GenerationService))
    company = c.resolve(CompanyService).list()[0]

    summary = batch.process_zip(zip_path, company, form_date=date(2026, 7, 24), profession=None)
    assert summary.ok_count == 2
    assert summary.total == 2
    assert len(list(summary.output_dir.glob("*.pdf"))) == 2
    assert str(summary.output_dir).find("Desktop") != -1  # saved to Desktop
