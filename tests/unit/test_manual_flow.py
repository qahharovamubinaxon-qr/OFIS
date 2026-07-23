"""Manual-entry builder + the full manual generation path via the controller."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

from src.ai.fake_provider import FakeProvider
from src.ai.manager import AiManager
from src.controllers.process_controller import ProcessController
from src.ocr.service import OcrService
from src.services.manual_entry import build_employee

ROOT = Path(__file__).resolve().parents[2]
HAS_TEMPLATE = (ROOT / "templates" / "mvd_prilozhenie_7" / "template.pdf").exists()

_VALUES = {
    "surname": "ЮЛДАШЕВ", "name": "БЕКЗОД", "patronymic": "УГЛИ",
    "citizenship": "УЗБЕКИСТАН", "birth_date": "15.03.1992",
    "passport_series": "CA", "passport_number": "5512345678",
    "passport_issue_date": "20.06.2019", "passport_issued_by": "МВД",
    "patent_series": "77", "patent_number": "2612345678",
    "patent_issue_date": "10.05.2026", "patent_issued_by": "ОВМ",
    "profession": "",  # empty → default
}


def test_build_employee_parses_dates_and_defaults() -> None:
    emp = build_employee(_VALUES, uuid4(), contract_date=date(2026, 7, 23))
    assert emp.passport.surname == "ЮЛДАШЕВ"
    assert emp.passport.birth_date == date(1992, 3, 15)
    assert emp.patent is not None
    assert emp.patent.issue_date == date(2026, 5, 10)
    assert emp.profession == "ПОДСОБНЫЙ РАБОЧИЙ"  # blank → default


@pytest.mark.skipif(not HAS_TEMPLATE, reason="template missing")
def test_manual_generation_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    from src.config import paths

    paths.data_dir.cache_clear()
    from src.app import build_container
    from src.services.company_service import CompanyService
    from src.services.generation_service import GenerationService

    c = build_container()
    controller = ProcessController(
        c.resolve(CompanyService),
        OcrService(AiManager([FakeProvider()])),
        c.resolve(GenerationService),
    )
    company = controller.companies()[0]
    result = controller.generate_from_manual(
        company, _VALUES, form_date=date(2026, 7, 23), profession=None
    )
    assert result.pdf_path.exists()
    assert result.pdf_path.name == "ЮЛДАШЕВ_БЕКЗОД.pdf"
