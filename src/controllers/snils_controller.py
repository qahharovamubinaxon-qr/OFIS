"""СНИЛС controller — a passport and two things the operator types."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.common.logging import get_logger
from src.domain.documents import Passport
from src.ocr.service import OcrService
from src.services.snils_service import SnilsResult, SnilsService

log = get_logger(__name__)


class SnilsController:
    def __init__(self, ocr: OcrService, service: SnilsService) -> None:
        self._ocr = ocr
        self._service = service

    # ------------------------------------------------------------- state
    def ai_available(self) -> bool:
        return self._ocr.available()

    def number(self) -> str:
        return self._service.number()

    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, blank: Path) -> Path:
        return self._service.add_template(name, blank)

    def remove_template(self, folder: Path) -> None:
        self._service.remove_template(folder)

    # ---------------------------------------------------------- passport
    def read_passport(self, image: bytes) -> dict[str, str]:
        """The four fields this sheet needs, ready to be checked.

        «Место рождения» on this form is the COUNTRY, which is what the reader
        is already asked for — a town there would be wrong on the sheet.
        """
        passport: Passport = self._ocr.read_passport(image)
        return {
            "surname": (passport.surname or "").strip(),
            "name": (passport.name or "").strip(),
            "patronymic": (passport.patronymic or "").strip(),
            "birth_date": (passport.birth_date.strftime("%d.%m.%Y")
                           if passport.birth_date else ""),
            "birth_place": (passport.birth_place or passport.nationality
                            or "").strip(),
            "gender": (passport.gender.value if passport.gender else ""),
        }

    # --------------------------------------------------------- printing
    def generate(self, **kwargs) -> SnilsResult:
        return self._service.generate(**kwargs)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return Path(path).read_bytes()

    @staticmethod
    def parse_date(text: str) -> date | None:
        text = (text or "").strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None
