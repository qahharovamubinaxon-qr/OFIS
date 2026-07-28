"""Coordinates СТРАХОВКА МАШИНАГА for the UI.

Six photographs go in — the СТС front and back, and up to four driving
licences — and one filled policy comes out.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

from src.common.logging import get_logger
from src.domain.insurance_template import InsuranceTemplate
from src.domain.vehicle import DriverLicence, Sts
from src.ocr.service import OcrService
from src.services.insurance_service import (
    InsuranceResult,
    InsuranceService,
    InsuranceTemplateService,
    cover_until,
)

log = get_logger(__name__)


class InsuranceController:
    def __init__(self, templates: InsuranceTemplateService, ocr: OcrService,
                 insurance: InsuranceService) -> None:
        self._templates = templates
        self._ocr = ocr
        self._insurance = insurance

    # ------------------------------------------------------------ templates
    def templates(self) -> list[InsuranceTemplate]:
        self._templates.seed_bundled()
        return self._templates.list()

    def add_template(self, name: str, code: str, source: Path, *,
                     insurer: str = "", firm: str = "") -> InsuranceTemplate:
        return self._templates.create(name, code, source,
                                      insurer=insurer, firm=firm)

    def archive_template(self, template_id: UUID) -> None:
        self._templates.archive(template_id)

    # ----------------------------------------------------------------- dates
    @staticmethod
    def cover_until(start: date) -> date:
        """A year of cover ends the day before the anniversary."""
        return cover_until(start)

    def ai_available(self) -> bool:
        return self._ocr.available()

    # -------------------------------------------------------------- the run
    def generate_from_images(
        self,
        template: InsuranceTemplate,
        sts_front: bytes,
        sts_back: bytes | None,
        licences: list[bytes],
        *,
        start: date,
        unlimited: bool,
        policy_holder: str = "",
    ) -> InsuranceResult:
        sts = self._ocr.read_sts(sts_front, sts_back)
        drivers: list[DriverLicence] = [
            self._ocr.read_licence(image) for image in licences if image]
        return self._insurance.generate(
            sts, drivers, template, start=start, unlimited=unlimited,
            policy_holder=policy_holder)

    def generate(self, template: InsuranceTemplate, sts: Sts,
                 drivers: list[DriverLicence], *, start: date, unlimited: bool,
                 policy_holder: str = "") -> InsuranceResult:
        """Same run, when the operator typed the data instead of uploading it."""
        return self._insurance.generate(
            sts, drivers, template, start=start, unlimited=unlimited,
            policy_holder=policy_holder)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
