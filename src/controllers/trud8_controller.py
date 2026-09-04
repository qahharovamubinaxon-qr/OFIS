"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — reading the documents and printing both papers.

Passport + patent photographs; the ФИО comes off the patent (Russian,
ready) through the same merge every other section leans on. Where each
value lands is the office's own doing — see :mod:`src.pdf.trud8_fields`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.domain.documents import Passport, Patent
from src.ocr.service import OcrService
from src.pdf.trud8_fields import Field
from src.pdf.trud8_renderer import Trud8Data
from src.services.trud8_service import Trud8Result, Trud8Service

log = get_logger(__name__)


class Trud8Controller:
    def __init__(self, ocr: OcrService, service: Trud8Service) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- store
    def firms(self) -> list[Path]:
        return self._service.firms()

    def add_firm(self, name: str) -> Path:
        return self._service.add_firm(name)

    def remove_firm(self, firm: Path) -> None:
        self._service.remove_firm(firm)

    # ------------------------------------------------------------ blanks
    def blank(self, firm: Path, kind: str) -> Path | None:
        return self._service.blank(firm, kind)

    def set_blank(self, firm: Path, kind: str, source: Path) -> Path:
        return self._service.set_blank(firm, kind, source)

    def pages(self, firm: Path, kind: str) -> int:
        return self._service.pages(firm, kind)

    # ------------------------------------------------------------ fields
    def fields(self, firm: Path, kind: str) -> list[Field]:
        return self._service.fields(firm, kind)

    def save_fields(self, firm: Path, kind: str, fields: list[Field]) -> Path:
        return self._service.save_fields(firm, kind, fields)

    # ------------------------------------------------------------ reading
    @staticmethod
    def read_image(path: Path) -> bytes:
        """The dropped file's bytes. Every section's controller carries this;
        its absence here is what made ТРУД's read crash the instant a passport
        was dropped — «AttributeError: no attribute 'read_image'»."""
        return Path(path).read_bytes()

    def read_documents(self, passport_image: bytes, patent_front: bytes | None,
                       patent_back: bytes | None) -> tuple[Passport, Patent]:
        passport, patent = self._ocr.read_documents(
            passport_image, patent_front, patent_back)
        return passport, patent or Patent(number="", profession="")

    # ----------------------------------------------------------- printing
    def generate(self, *, firm: Path | None, passport: Passport,
                 patent: Patent, profession: str, deal_date: date,
                 want_pdf: bool = True) -> Trud8Result:
        data = self.data_of(passport, patent, profession, deal_date)
        return self._service.generate(data, firm, want_pdf=want_pdf)

    @staticmethod
    def data_of(passport: Passport, patent: Patent, profession: str,
                deal_date: date) -> Trud8Data:
        return Trud8Data(
            surname=passport.surname or patent.holder_surname or "",
            name=passport.name or patent.holder_name or "",
            patronymic=passport.patronymic or patent.holder_patronymic or "",
            gender=(passport.gender.value
                    if getattr(passport.gender, "value", None)
                    else str(passport.gender or "")),
            citizenship=(passport.nationality or patent.holder_citizenship
                         or ""),
            birth_date=passport.birth_date,
            pass_series=passport.series or "",
            pass_number=passport.number or "",
            pass_issued=passport.issue_date,
            pass_issued_by=passport.issued_by or "",
            pat_series=patent.series or "",
            pat_number=patent.number or "",
            pat_blank_series=patent.blank_series or "",
            pat_blank_number=patent.blank_number or "",
            pat_issued=patent.issue_date,
            pat_valid_to=patent.valid_to,
            pat_issued_by=patent.issued_by or "",
            profession=profession or (patent.profession or ""),
            deal_date=deal_date)
