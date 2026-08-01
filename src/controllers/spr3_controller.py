"""3-СПРАВКА — reading the two photographs and printing the certificate.

Two images stand behind one certificate: the passport (its numbers and dates),
and a second document — patent or миграционная карта — whose only job is the
ФИО written in Russian, ready for the form. Both go through
:meth:`OcrService.read_documents`, whose merge already prefers the second
document's Russian name over the passport's transliteration.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.common.logging import get_logger
from src.domain.documents import Passport
from src.ocr.service import OcrService
from src.pdf.spr3_renderer import Spr3Data, year_minus_day
from src.services.spr3_service import Spr3Result, Spr3Service

log = get_logger(__name__)


class Spr3Controller:
    def __init__(self, ocr: OcrService, service: Spr3Service) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- store
    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, source: Path) -> Path:
        return self._service.add_template(name, source)

    def remove_template(self, template: Path) -> None:
        self._service.remove_template(template)

    def layout(self, template: Path | None) -> dict:
        return self._service.layout(template)

    def save_layout(self, template: Path, layout: dict):
        return self._service.save_layout(template, layout)

    def reset_layout(self, template: Path) -> None:
        self._service.reset_layout(template)

    # ------------------------------------------------------------ reading
    def read_documents(self, passport_image: bytes,
                       name_image: bytes | None) -> Passport:
        """The merged worker: Russian ФИО off the second photo when there is
        one, everything else off the passport."""
        passport, _patent = self._ocr.read_documents(passport_image, name_image)
        return passport

    @staticmethod
    def parse_date(text: str) -> date | None:
        text = (text or "").strip()
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    # ----------------------------------------------------------- printing
    def generate(self, *, template: Path | None, passport: Passport,
                 valid_from: date, address: str) -> Spr3Result:
        data = Spr3Data(
            surname=passport.surname or "",
            name=passport.name or "",
            patronymic=passport.patronymic or "",
            citizenship=passport.nationality or "",
            birth_date=passport.birth_date,
            pass_series=passport.series or "",
            pass_number=passport.number or "",
            valid_from=valid_from,
            address=address)
        return self._service.generate(data, template)

    @staticmethod
    def until(valid_from: date | None) -> date | None:
        return year_minus_day(valid_from)
