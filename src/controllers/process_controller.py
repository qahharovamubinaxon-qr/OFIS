"""Coordinates the process-employee use-case for the UI.

Holds no business logic itself — it calls services and returns plain results the
view can show. Both entry points converge on GenerationService.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

from src.common.logging import get_logger
from src.domain.company import Company
from src.ocr.service import OcrService
from src.services.company_service import CompanyService
from src.services.generation_service import GenerationResult, GenerationService
from src.services.manual_entry import build_employee

log = get_logger(__name__)


class ProcessController:
    def __init__(
        self,
        companies: CompanyService,
        ocr: OcrService,
        generation: GenerationService,
    ) -> None:
        self._companies = companies
        self._ocr = ocr
        self._generation = generation

    def companies(self) -> list[Company]:
        return self._companies.list()

    def ai_available(self) -> bool:
        return self._ocr.available()

    def next_reg_number(self) -> int:
        return self._generation.next_reg_number()

    # -- AI mode: read passport + patent images, then generate --------------
    def generate_from_images(
        self,
        company: Company,
        passport_image: bytes,
        patent_image: bytes | None,
        patent_back_image: bytes | None = None,
        *,
        form_date: date,
        profession: str | None,
    ) -> GenerationResult:
        passport = self._ocr.read_passport(passport_image)
        patent = (
            self._ocr.read_patent(patent_image, patent_back_image) if patent_image else None
        )
        from src.domain.employee import Employee

        employee = Employee(
            company_id=company.id, passport=passport, patent=patent,
            profession=profession or (patent.profession if patent else "ПОДСОБНЫЙ РАБОЧИЙ"),
            contract_date=form_date,
        )
        return self._generation.generate(
            employee, company, form_date=form_date, profession=profession
        )

    # -- Manual mode: build from the 16-field table ------------------------
    def generate_from_manual(
        self,
        company: Company,
        values: dict[str, str],
        *,
        form_date: date,
        profession: str | None,
    ) -> GenerationResult:
        employee = build_employee(values, company.id, contract_date=form_date)
        return self._generation.generate(
            employee, company, form_date=form_date, profession=profession or employee.profession
        )

    # -- Bulk mode: a ZIP of per-worker folders → one PDF each ------------
    def process_zip(
        self,
        zip_path: Path,
        company: Company,
        *,
        form_date: date,
        profession: str | None,
        on_progress=None,
    ):
        from src.services.batch_service import BatchService

        batch = BatchService(self._ocr, self._generation)
        return batch.process_zip(
            zip_path, company, form_date=form_date, profession=profession, on_progress=on_progress
        )

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
