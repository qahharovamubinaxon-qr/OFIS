"""ППУ controller — the регистрация, the worker's photograph, and one date.

Everything the pair says is already on the регистрация; the operator supplies
only the day it starts. The reader's answers are suggestions and every one of
them stays editable on screen — a регистрация photographed badly is common,
and a wrong address on a filed pair is not.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.common.logging import get_logger
from src.ocr.service import OcrService
from src.services.ppu_service import PpuResult, PpuService

log = get_logger(__name__)


class PpuController:
    def __init__(self, ocr: OcrService, service: PpuService) -> None:
        self._ocr = ocr
        self._service = service

    # ------------------------------------------------------------- state
    def ai_available(self) -> bool:
        return self._ocr.available()

    def number(self) -> str:
        return self._service.number()

    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, front: Path, back: Path) -> Path:
        return self._service.add_template(name, front, back)

    # ----------------------------------------------------- registration
    def read_registration(self, image: bytes) -> dict[str, str]:
        """The pair's fields, off the регистрация, ready to be checked."""
        return self._ocr.read_registration(image)

    # --------------------------------------------------------- printing
    def generate(self, **kwargs) -> PpuResult:
        return self._service.generate(**kwargs)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return Path(path).read_bytes()

    @staticmethod
    def parse_date(text: str) -> date | None:
        text = (text or "").strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None
