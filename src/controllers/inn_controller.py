"""Coordinates the ИНН use-case: a passport or patent photo → the record sheet."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.ocr.service import OcrService
from src.services.inn_service import InnResult, InnService

log = get_logger(__name__)


class InnController:
    def __init__(self, ocr: OcrService, inn: InnService) -> None:
        self._ocr = ocr
        self._inn = inn

    def ai_available(self) -> bool:
        return self._ocr.available()

    def generate_from_image(
        self,
        image: bytes,
        *,
        inn: str,
        form_date: date,
    ) -> InnResult:
        """The upload may be a passport or a patent — both print the worker's
        ФИО, date of birth and citizenship, which is all the sheet needs."""
        passport = self._ocr.read_passport(image)
        return self._inn.generate(passport, inn=inn, form_date=form_date)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
