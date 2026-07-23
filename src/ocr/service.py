"""OCR service: read passport + patent images into validated domain models.

It orchestrates the provider (via AiManager) and normalization, and never knows
which provider ran. Output is a validated (Passport, Patent) pair the controller
assembles into an Employee with the operator-chosen company, date and должность.
"""

from __future__ import annotations

from datetime import date

from src.ai.manager import AiManager
from src.ai.prompts import prompt_for
from src.common.logging import get_logger
from src.domain.documents import Passport, Patent
from src.domain.enums import DocType

log = get_logger(__name__)


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


class OcrService:
    def __init__(self, ai: AiManager) -> None:
        self._ai = ai

    def available(self) -> bool:
        return self._ai.available()

    def read_passport(self, image: bytes) -> Passport:
        f = self._ai.extract(image, DocType.PASSPORT, prompt_for(DocType.PASSPORT)).fields
        return Passport(
            surname=f.get("surname", ""),
            name=f.get("name", ""),
            patronymic=f.get("patronymic") or None,
            nationality=f.get("nationality") or None,
            series=f.get("series") or None,
            number=f.get("number", ""),
            birth_date=_parse_date(f.get("birth_date", "")),
            issue_date=_parse_date(f.get("issue_date", "")),
            issued_by=f.get("issued_by") or None,
        )

    def read_patent(self, image: bytes) -> Patent:
        f = self._ai.extract(image, DocType.PATENT, prompt_for(DocType.PATENT)).fields
        return Patent(
            series=f.get("series") or None,
            number=f.get("number", ""),
            issue_date=_parse_date(f.get("issue_date", "")),
            issued_by=f.get("issued_by") or None,
            profession=f.get("profession", "") or "ПОДСОБНЫЙ РАБОЧИЙ",
        )
