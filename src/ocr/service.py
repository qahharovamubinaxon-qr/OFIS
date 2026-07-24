"""OCR service: read passport + patent images into validated domain models.

It orchestrates the provider (via AiManager) and normalization, and never knows
which provider ran. Output is a validated (Passport, Patent) pair the controller
assembles into an Employee with the operator-chosen company, date and должность.
"""

from __future__ import annotations

from datetime import date

from src.ai.manager import AiManager
from src.ai.prompts import patent_back_prompt, prompt_for
from src.common.logging import get_logger
from src.domain.documents import Passport, Patent
from src.domain.enums import DocType
from src.ocr.translit import to_cyrillic

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
            surname=to_cyrillic(f.get("surname", "")),
            name=to_cyrillic(f.get("name", "")),
            patronymic=to_cyrillic(f.get("patronymic", "")) or None,
            nationality=to_cyrillic(f.get("nationality", "")) or None,
            series=f.get("series") or None,  # series/number stay as printed
            number=f.get("number", ""),
            birth_date=_parse_date(f.get("birth_date", "")),
            issue_date=_parse_date(f.get("issue_date", "")),
            issued_by=to_cyrillic(f.get("issued_by", "")) or None,
        )

    def read_patent(self, front: bytes, back: bytes | None = None) -> Patent:
        """Read the patent. The FRONT gives серия/номер/профессия; the BACK (if
        supplied) gives дата выдачи + кем выдан — which is where they are printed.
        """
        f = self._ai.extract(front, DocType.PATENT, prompt_for(DocType.PATENT)).fields
        issue_date = _parse_date(f.get("issue_date", ""))
        issued_by = f.get("issued_by") or None
        if back is not None:
            b = self._ai.extract(back, DocType.PATENT, patent_back_prompt()).fields
            issue_date = _parse_date(b.get("issue_date", "")) or issue_date
            issued_by = (b.get("issued_by") or "").strip() or issued_by
        return Patent(
            series=f.get("series") or None,
            number=f.get("number", ""),
            issue_date=issue_date,
            issued_by=to_cyrillic(issued_by or "") or None,
            profession=to_cyrillic(f.get("profession", "")) or "ПОДСОБНЫЙ РАБОЧИЙ",
            holder_surname=to_cyrillic(f.get("surname", "")) or None,
            holder_name=to_cyrillic(f.get("name", "")) or None,
            holder_patronymic=to_cyrillic(f.get("patronymic", "")) or None,
        )

    def read_documents(
        self, passport_image: bytes, patent_front: bytes | None = None, patent_back: bytes | None = None
    ) -> tuple[Passport, Patent | None]:
        """Read passport + patent and return a consistent (Passport, Patent).

        Names come from the PATENT when it carries them (it prints ФИО in Russian,
        so it is reliable even for non-Cyrillic passports); the passport still
        supplies citizenship, birth date, series, number, issue date and issuer.
        """
        passport = self.read_passport(passport_image)
        patent = self.read_patent(patent_front, patent_back) if patent_front else None
        if patent is not None and patent.holder_surname:
            passport = passport.model_copy(
                update={
                    "surname": patent.holder_surname,
                    "name": patent.holder_name or passport.name,
                    "patronymic": patent.holder_patronymic or passport.patronymic,
                }
            )
        return passport, patent
