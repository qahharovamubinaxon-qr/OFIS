"""СЕРТИФИКАТ controller — the student's passport and what the operator types.

The passport is read the way every other section reads one, so the same office
rules hold here (see :mod:`src.domain.passport_rules`). The certificate asks for
nothing but the name, so only the Ф.И.О. is taken off it — the Latin line under
the Cyrillic one is worked out from that name, not read separately.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.domain.documents import Passport
from src.ocr.service import OcrService
from src.services.sertifikat_service import (
    SertifikatResult,
    SertifikatService,
)

log = get_logger(__name__)


class SertifikatController:
    def __init__(self, ocr: OcrService, service: SertifikatService) -> None:
        self._ocr = ocr
        self._service = service

    # ------------------------------------------------------------- state
    def ai_available(self) -> bool:
        return self._ocr.available()

    def blocks(self) -> tuple[str, str]:
        return self._service.blocks()

    def city(self) -> str:
        return self._service.city()

    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, page1: Path, page2: Path) -> Path:
        return self._service.add_template(name, page1, page2)

    # ---------------------------------------------------------- passport
    def read_passport(self, image: bytes) -> dict[str, str]:
        """The three name fields, ready to be checked and corrected."""
        passport: Passport = self._ocr.read_passport(image)
        return {
            "surname": (passport.surname or "").strip(),
            "name": (passport.name or "").strip(),
            "patronymic": (passport.patronymic or "").strip(),
        }

    # --------------------------------------------------------- printing
    def generate(self, **kwargs) -> SertifikatResult:
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
