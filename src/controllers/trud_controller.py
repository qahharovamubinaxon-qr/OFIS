"""Coordinates the Трудовой-Уведомления use-case for the UI."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

from src.common.logging import get_logger
from src.domain.trud_firm import TrudFirm
from src.ocr.service import OcrService
from src.services.trud_service import TrudFirmService, TrudResult, TrudService

log = get_logger(__name__)


class TrudController:
    def __init__(self, firms: TrudFirmService, ocr: OcrService, trud: TrudService) -> None:
        self._firms = firms
        self._ocr = ocr
        self._trud = trud

    def firms(self) -> list[TrudFirm]:
        return self._firms.list()

    def add_firm(self, name: str, code: str, trud_tpl: Path, uved_tpl: Path) -> TrudFirm:
        return self._firms.create(name, code, trud_tpl, uved_tpl)

    def archive_firm(self, firm_id: UUID) -> None:
        self._firms.archive(firm_id)

    def ai_available(self) -> bool:
        return self._ocr.available()

    def generate_from_images(
        self,
        firm: TrudFirm,
        passport_image: bytes,
        patent_image: bytes | None,
        patent_back_image: bytes | None = None,
        *,
        form_date: date,
        profession: str | None,
    ) -> TrudResult:
        passport, patent = self._ocr.read_documents(
            passport_image, patent_image, patent_back_image
        )
        return self._trud.generate(
            passport, patent, firm, form_date=form_date, profession=profession
        )

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
