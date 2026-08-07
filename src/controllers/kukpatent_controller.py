"""КУК ПАТЕНТ — reading the worker's passport and printing his card.

The bridge and nothing more. The one thing worth saying here is what happens
to the photograph: it is cut ONCE, by the same `prepare_portrait` every other
section uses, so a worker's face on this card is the same crop as on his
badge and his patent card — 3×4, head and shoulders, on white.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.ocr.service import OcrService
from src.pdf.kukpatent_renderer import KukPatentData
from src.pdf.kukpatent_spec import BACK, FRONT, SIDE_NAMES, SIDES
from src.services import kukpatent_service
from src.services.kukpatent_service import KukPatentResult, KukPatentService


class KukPatentController:
    def __init__(self, ocr: OcrService, service: KukPatentService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # -------------------------------------------------------------- sides
    @staticmethod
    def sides() -> tuple[str, ...]:
        return SIDES

    @staticmethod
    def side_names() -> dict[str, str]:
        return dict(SIDE_NAMES)

    @staticmethod
    def blanks() -> dict[str, Path]:
        return kukpatent_service.blanks()

    @staticmethod
    def set_blank(side: str, source: Path) -> Path:
        return kukpatent_service.set_blank(side, source)

    @staticmethod
    def clear_blank(side: str) -> None:
        kukpatent_service.clear_blank(side)

    # -------------------------------------------------------------- firms
    @staticmethod
    def firms() -> list[str]:
        return kukpatent_service.firms()

    @staticmethod
    def remember_firm(firm: str) -> None:
        kukpatent_service.remember_firm(firm)

    @staticmethod
    def forget_firm(firm: str) -> None:
        kukpatent_service.forget_firm(firm)

    # ------------------------------------------------------------ numbers
    @staticmethod
    def next_number() -> str:
        return kukpatent_service.next_number()

    # ------------------------------------------------------------- layout
    @staticmethod
    def layout() -> dict:
        return kukpatent_service.load_layout()

    @staticmethod
    def save_layout(layout: dict) -> None:
        kukpatent_service.save_layout(layout)

    # ------------------------------------------------------------- photo
    @staticmethod
    def portrait(image: bytes) -> bytes | None:
        """The worker's face, cut to the card's 3×4 window on white.

        One cut, everywhere — the same call the badge, the patent card and
        разрешение make, so the same worker never appears cropped two ways.
        """
        from src.services.photo_service import prepare_portrait

        return prepare_portrait(image, aspect=0.75)

    # ------------------------------------------------------------ reading
    def read_passport(self, image: bytes, *, firm: str, series: str,
                      number: str, issued: date | None,
                      card_no: str = "",
                      photo: bytes | None = None) -> KukPatentData:
        passport = self._ocr.read_passport(image)
        return kukpatent_service.data_of(
            passport, firm=firm, series=series, number=number, issued=issued,
            card_no=card_no,
            photo_png=self.portrait(photo) if photo else None)

    # ----------------------------------------------------------- printing
    def generate(self, data: KukPatentData) -> KukPatentResult:
        return self._service.generate(data)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()


__all__ = ["BACK", "FRONT", "KukPatentController"]
