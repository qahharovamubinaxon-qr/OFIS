"""Company + generation services end-to-end (real SQLite + real template)."""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path
from uuid import uuid4

import fitz
import pytest

from src.app import build_container
from src.domain.documents import Passport, Patent
from src.domain.employee import Employee
from src.services.company_service import CompanyService
from src.services.generation_service import GenerationService

ROOT = Path(__file__).resolve().parents[2]
HAS_TEMPLATE = (ROOT / "templates" / "mvd_prilozhenie_7" / "template.pdf").exists()


@pytest.fixture()
def container(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    # paths caches data_dir(); clear it so the temp dir takes effect
    from src.config import paths

    paths.data_dir.cache_clear()
    return build_container()


def _employee(company_id) -> Employee:
    return Employee(
        company_id=company_id,
        passport=Passport(surname="КАРИМОВ", name="ОТАБЕК", number="123456789",
                          nationality="УЗБЕКИСТАН", birth_date=date(1990, 1, 1),
                          issue_date=date(2015, 1, 1), issued_by="МВД"),
        patent=Patent(number="7712345678", series="77", profession="ПОДСОБНЫЙ РАБОЧИЙ",
                      issue_date=date(2026, 5, 10), issued_by="ОВМ"),
        profession="ПОДСОБНЫЙ РАБОЧИЙ", contract_date=date(2026, 7, 23),
    )


@pytest.mark.skipif(not HAS_TEMPLATE, reason="template missing")
def test_seed_and_generate(container) -> None:
    companies = container.resolve(CompanyService)
    gen = container.resolve(GenerationService)
    assert companies.count() == 1
    company = companies.list()[0]

    start = gen.next_reg_number()
    result = gen.generate(_employee(company.id), company, form_date=date(2026, 7, 23))

    assert result.pdf_path.exists()
    assert result.pdf_path.name == "КАРИМОВ_ОТАБЕК.pdf"
    assert result.reg_number == start
    doc = fitz.open(str(result.pdf_path))
    assert "КАРИМОВ" in doc[1].get_text().replace(" ", "")
    doc.close()


@pytest.mark.skipif(not HAS_TEMPLATE, reason="template missing")
def test_dedupe_and_counter(container) -> None:
    companies = container.resolve(CompanyService)
    gen = container.resolve(GenerationService)
    company = companies.list()[0]

    r1 = gen.generate(_employee(company.id), company, form_date=date(2026, 7, 23))
    r2 = gen.generate(_employee(company.id), company, form_date=date(2026, 7, 23))
    assert r2.reg_number == r1.reg_number + 1
    assert r1.pdf_path.name != r2.pdf_path.name  # deduped filename
