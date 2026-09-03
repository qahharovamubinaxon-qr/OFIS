"""Coordinates the СФЕРА use-case for the UI.

Reads the student ФИО from a passport (OCR), takes the uploaded photo + chosen
profession + date, and calls SveraService to produce the 2-page PDF.

The centre found OCR occasionally misreading a surname, so any of the three
name parts may be typed instead — a typed part always wins over the passport,
and with all three typed no passport is needed at all.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.domain.documents import Passport
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

    def read_passport(self, passport_image: bytes) -> Passport:
        """The student's ФИО off the passport, for the operator to check in the
        name boxes before the СФЕРА cert is printed."""
        return self._ocr.read_passport(passport_image)

    def generate_from_images(
        self,
        profession: Profession,
        passport_image: bytes | None,
        photo_path: Path,
        *,
        issue_date: date,
        surname: str = "",
        name: str = "",
        patronymic: str = "",
    ) -> SveraResult:
        passport = self._student(passport_image, surname, name, patronymic)
        return self._svera.generate(
            passport, profession, issue_date=issue_date, photo_path=photo_path
        )

    def _student(self, passport_image: bytes | None, surname: str,
                 name: str, patronymic: str) -> Passport:
        """The student's name: typed where typed, read where not."""
        surname, name = surname.strip(), name.strip()
        patronymic = patronymic.strip()
        if passport_image is None:
            if not (surname and name):
                raise OfisError(
                    "Паспорт юкланмаса — камида фамилия ва исмни ёзинг.")
            return Passport(surname=surname, name=name,
                            patronymic=patronymic or None, number="")

        read = self._ocr.read_passport(passport_image)
        if not (surname or name or patronymic):
            return read
        return read.model_copy(update={
            "surname": surname or read.surname,
            "name": name or read.name,
            "patronymic": patronymic or read.patronymic,
        })

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
