"""РАЗРЕШЕНИЯ controller — passport + photograph + what the operator types.

The passport is read the way every other section reads one, so the same rules
hold here: a Tajik passport arrives with its серия already dropped and the nine
digits alone, and «кем выдан» already in Russian (see
:mod:`src.domain.passport_rules`). Nothing about the card asks for the issuing
office, so only the ФИО, the birth date, the citizenship and the passport
itself are taken off it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.domain.documents import Passport
from src.ocr.service import OcrService
from src.services.razreshenie_service import (
    Firm,
    RazreshenieResult,
    RazreshenieService,
)

log = get_logger(__name__)


class RazreshenieController:
    def __init__(self, ocr: OcrService, service: RazreshenieService) -> None:
        self._ocr = ocr
        self._service = service

    # ------------------------------------------------------------- state
    def ai_available(self) -> bool:
        return self._ocr.available()

    def next_numbers(self) -> tuple[str, str, str]:
        return self._service.next_numbers()

    def firm(self) -> Firm:
        return self._service.firm()

    def firms(self) -> list[Firm]:
        return self._service.firms()

    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, front: Path, back: Path) -> Path:
        return self._service.add_template(name, front, back)

    # ---------------------------------------------------------- passport
    def read_passport(self, image: bytes) -> dict[str, str]:
        """The card's own five fields, ready to be checked and corrected."""
        passport: Passport = self._ocr.read_passport(image)
        document = f"{passport.series or ''}{passport.number or ''}".strip()
        return {
            "surname": (passport.surname or "").strip(),
            "name": (passport.name or "").strip(),
            "patronymic": (passport.patronymic or "").strip(),
            "birth_date": (passport.birth_date.strftime("%d.%m.%Y")
                           if passport.birth_date else ""),
            "citizenship": (passport.nationality or "").strip(),
            "document": document,
        }

    # --------------------------------------------------------- printing
    def generate(self, **kwargs) -> RazreshenieResult:
        return self._service.generate(**kwargs)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return Path(path).read_bytes()

    @staticmethod
    def parse_date(text: str) -> date | None:
        text = (text or "").strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            try:
                from datetime import datetime

                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None
