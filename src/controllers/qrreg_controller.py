"""КРКОД РЕГ — reading the two photographs and running the QR chain."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.common.logging import get_logger
from src.domain.documents import Passport
from src.ocr.service import OcrService
from src.pdf.qrreg_renderer import QrRegData
from src.services.qrreg_service import QrRegResult, QrRegService

log = get_logger(__name__)


class QrRegController:
    def __init__(self, ocr: OcrService, service: QrRegService) -> None:
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

    def podt_template(self) -> Path | None:
        return self._service.podt_template()

    def set_podt_template(self, source: Path) -> Path:
        return self._service.set_podt_template(source)

    def layout(self, template: Path | None) -> dict:
        return self._service.layout(template)

    def save_layout(self, template: Path, layout: dict):
        return self._service.save_layout(template, layout)

    def podt_layout(self) -> dict:
        return self._service.podt_layout()

    def save_podt_layout(self, layout: dict) -> None:
        self._service.save_podt_layout(layout)

    def addresses(self) -> list[dict]:
        return self._service.addresses()

    def address_for_blank(self, template) -> dict | None:
        """The address last registered on this blank — its usual one."""
        return self._service.address_for_blank(template)

    @staticmethod
    def address_label(entry: dict) -> str:
        from src.services.qrreg_service import address_label

        return address_label(entry)

    # ------------------------------------------------------------ reading
    def read_documents(self, passport_image: bytes,
                       patent_image: bytes | None) -> Passport:
        """Russian ФИО off the patent when it is there; the rest off the
        passport — the house merge."""
        passport, _patent = self._ocr.read_documents(passport_image,
                                                     patent_image)
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
                 valid_from: date, valid_to: date, address: dict,
                 code: str) -> QrRegResult:
        data = QrRegData(
            surname=passport.surname or "",
            name=passport.name or "",
            patronymic=passport.patronymic or "",
            citizenship=passport.nationality or "",
            birth_date=passport.birth_date,
            gender=(passport.gender.value
                    if getattr(passport.gender, "value", None)
                    else str(passport.gender or "")),
            pass_series=passport.series or "",
            pass_number=passport.number or "",
            pass_issued=passport.issue_date,
            pass_expiry=passport.expiry_date,
            valid_from=valid_from, valid_to=valid_to,
            addr_subject=str(address.get("addr_subject") or ""),
            addr_district=str(address.get("addr_district") or ""),
            addr_punkt=str(address.get("addr_punkt") or ""),
            addr_street=str(address.get("addr_street") or ""),
            dom=str(address.get("dom") or ""),
            korpus=str(address.get("korpus") or ""),
            kvartira=str(address.get("kvartira") or ""),
            code=code,
            host_surname=str(address.get("host_surname") or ""),
            host_name=str(address.get("host_name") or ""),
            host_patronymic=str(address.get("host_patronymic") or ""))
        return self._service.generate(data, template)
