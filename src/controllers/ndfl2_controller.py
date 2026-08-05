"""2 НДФЛ — reading the two documents and printing the справка."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from src.common.logging import get_logger
from src.ocr.service import OcrService
from src.services import ndfl2_service
from src.services.ndfl2_service import Ndfl2Result, Ndfl2Service

log = get_logger(__name__)


class Ndfl2Controller:
    def __init__(self, ocr: OcrService, service: Ndfl2Service) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # -------------------------------------------------------------- firms
    def firms(self) -> list[Path]:
        return self._service.firms()

    def add_firm(self, name: str, blank: Path) -> Path:
        return self._service.add_firm(name, blank)

    def remove_firm(self, firm: Path) -> None:
        self._service.remove_firm(firm)

    def blank(self, firm: Path) -> Path | None:
        return self._service.blank(firm)

    def layout(self, firm: Path) -> dict:
        """What «📐» opens with — the table measured off this firm's sheet
        when it has never been arranged."""
        return ndfl2_service.table_of(firm)

    def save_layout(self, firm: Path, layout: dict) -> None:
        ndfl2_service.save_layout(firm, layout)

    # ----------------------------------------------------------- printing
    def generate_from_images(
        self,
        firm: Path,
        passport_image: bytes,
        patent_image: bytes | None,
        *,
        months: dict[int, Decimal],
        year: int,
        form_date: date | None = None,
    ) -> Ndfl2Result:
        passport, patent = self._ocr.read_documents(
            passport_image, patent_image, None)
        inn = ""
        if patent_image is not None:
            try:
                inn = self._ocr.read_inn(patent_image)
            except Exception as exc:                  # noqa: BLE001
                log.warning("2НДФЛ: ИНН ўқилмади — %s", exc)
        data = ndfl2_service.data_of(passport, patent, months=months,
                                     year=year, form_date=form_date, inn=inn)
        return self._service.generate(data, firm)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
