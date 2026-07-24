"""Coordinates the СФЕРА use-case for the UI.

Reads the student ФИО from a passport (OCR), takes the uploaded photo + chosen
profession + date, and calls SveraService to produce the 2-page PDF.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.domain.profession import Profession
from src.ocr.service import OcrService
from src.services.profession_service import ProfessionService
from src.services.svera_service import SveraResult, SveraService

log = get_logger(__name__)


class SveraController:
    def __init__(
        self,
        professions: ProfessionService,
        ocr: OcrService,
        svera: SveraService,
    ) -> None:
        self._professions = professions
        self._ocr = ocr
        self._svera = svera

    def professions(self) -> list[Profession]:
        return self._professions.list()

    def add_profession(self, name: str, note: str | None, grade: int = 5) -> Profession:
        return self._professions.add(name, note, grade)

    def ai_available(self) -> bool:
        return self._ocr.available()

    def next_po_number(self) -> int:
        return self._svera.next_po_number()

    def generate_from_images(
        self,
        profession: Profession,
        passport_image: bytes,
        photo_path: Path,
        *,
        issue_date: date,
    ) -> SveraResult:
        passport = self._ocr.read_passport(passport_image)
        return self._svera.generate(
            passport, profession, issue_date=issue_date, photo_path=photo_path
        )

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
