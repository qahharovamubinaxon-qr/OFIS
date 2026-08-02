"""СТРАХОВКА МАШИНАГА — reading the car's papers and printing the policy.

The СТС (front and back) names the car and its owner; up to four licence
photographs name the drivers. No licences means the policy covers anyone —
the upload itself decides which «птичка» the policy gets.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.domain.vehicle import DriverLicence
from src.ocr.service import OcrService
from src.pdf.osago_renderer import OsagoData
from src.services.osago_service import OsagoResult, OsagoService, cover_until

log = get_logger(__name__)


class OsagoController:
    def __init__(self, ocr: OcrService, service: OsagoService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- store
    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, source: Path,
                     base: str = "ingosstrah") -> Path:
        return self._service.add_template(name, source, base)

    def remove_template(self, template: Path) -> None:
        self._service.remove_template(template)

    def layout(self, template: Path | None) -> dict:
        return self._service.layout(template)

    def save_layout(self, template: Path, layout: dict):
        return self._service.save_layout(template, layout)

    def base_of(self, template: Path | None) -> str:
        return self._service.base_of(template)

    @staticmethod
    def cover_until(start: date) -> date:
        return cover_until(start)

    # ----------------------------------------------------------- printing
    def generate_from_images(self, *, template: Path | None,
                             sts_front: bytes, sts_back: bytes | None,
                             licences: list[bytes], start: date,
                             policy_no: str = "",
                             premium: str = "") -> OsagoResult:
        """The upload decides the cover: no licences → anyone may drive."""
        sts = self._ocr.read_sts(sts_front, sts_back)
        drivers: list[DriverLicence] = [
            self._ocr.read_licence(image) for image in licences if image]
        named = [d for d in drivers if not d.is_empty()]
        data = OsagoData(
            sts=sts, drivers=named, unlimited=not named,
            start=start, until=cover_until(start),
            policy_no=policy_no, premium=premium)
        return self._service.generate(data, template)
