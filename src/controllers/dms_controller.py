"""Coordinates the ДМС use-case: passport photo → OCR → filled policy PDF."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.ocr.service import OcrService
from src.services.dms_service import DmsResult, DmsService

log = get_logger(__name__)


class DmsController:
    def __init__(self, ocr: OcrService, dms: DmsService) -> None:
        self._ocr = ocr
        self._dms = dms

    def ai_available(self) -> bool:
        return self._ocr.available()

    def next_number(self) -> str:
        return self._dms.peek_number()

    def remaining(self) -> int:
        return self._dms.remaining()

    def generate_from_images(
        self,
        passport_image: bytes,
        *,
        start_date: date,
        phone: str,
        address: str,
        region: str | None = None,
    ) -> DmsResult:
        passport = self._ocr.read_passport(passport_image)
        return self._dms.generate(
            passport, start_date=start_date, phone=phone, address=address,
            region=region)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
