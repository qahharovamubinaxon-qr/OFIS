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

    def read_passport(self, passport_image: bytes):
        """What the passport says — for the operator to check before printing.

        Reading and printing used to be one press, so nobody ever saw what
        had been read until the policy came out with it on. The office asked
        for the two to be separate, and they are.
        """
        return self._ocr.read_passport(passport_image)

    def generate(self, passport, *, start_date: date, phone: str,
                 address: str, region: str | None = None) -> DmsResult:
        """The policy, from what is IN THE BOXES — not from what was read."""
        return self._dms.generate(
            passport, start_date=start_date, phone=phone, address=address,
            region=region)

    def generate_from_images(
        self,
        passport_image: bytes,
        *,
        start_date: date,
        phone: str,
        address: str,
        region: str | None = None,
    ) -> DmsResult:
        """Read and print in one go — kept for the bot, which has no screen."""
        return self.generate(
            self.read_passport(passport_image), start_date=start_date,
            phone=phone, address=address, region=region)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
