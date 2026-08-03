"""КУК ЧЕК — reading the patent card and printing the payment чек.

The patent card names the worker AND carries the ИНН — the same read the
ЧЕК section already trusts, borrowed whole.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.common.logging import get_logger
from src.controllers.chek_controller import ChekController
from src.ocr.service import OcrService
from src.pdf.kukchek_renderer import KukChekData
from src.services.kukchek_service import KukChekResult, KukChekService
from src.utils.rus_words import parse_amount

log = get_logger(__name__)


class KukChekController:
    def __init__(self, ocr: OcrService, service: KukChekService) -> None:
        self._ocr = ocr
        self._service = service
        self._reader = ChekController(ocr)

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- store
    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, source: Path) -> Path:
        return self._service.add_template(name, source)

    def remove_template(self, template: Path) -> None:
        self._service.remove_template(template)

    def stamp(self) -> Path | None:
        return self._service.stamp()

    def set_stamp(self, source: Path) -> Path:
        return self._service.set_stamp(source)

    def remove_stamp(self) -> None:
        self._service.remove_stamp()

    def layout(self, template: Path | None) -> dict:
        return self._service.layout(template)

    def save_layout(self, template: Path, layout: dict):
        return self._service.save_layout(template, layout)

    # ------------------------------------------------------------ reading
    def read_patent(self, image: bytes) -> dict[str, str]:
        """{fam, ism, otch, inn} — off the patent card."""
        return self._reader.read_patent_fields(image)

    # ----------------------------------------------------------- printing
    def generate(self, *, template: Path | None, fields: dict[str, str],
                 when: date, amount_text: str) -> KukChekResult:
        rubles, kopecks = parse_amount(amount_text)
        data = KukChekData(
            fam=fields.get("fam", ""), ism=fields.get("ism", ""),
            otch=fields.get("otch", ""), inn=fields.get("inn", ""),
            when=when, at=datetime.now(),
            rubles=rubles, kopecks=kopecks)
        return self._service.generate(data, template)
