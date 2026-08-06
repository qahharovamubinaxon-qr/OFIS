"""УЗБ СПРАВКАЛАР — reading the worker's passport and printing his four sheets.

The bridge and nothing more: the screen knows no service and no reader, and
the service knows no screen. Two things are worth reading here rather than
typing — the worker's own rows off his passport, and his ПИНФЛ out of the
strip at its foot, which the certificates name him by and the passport prints
nowhere else.
"""

from __future__ import annotations

from pathlib import Path

from src.ocr.service import OcrService
from src.pdf.uzbspravka_renderer import UzbData
from src.services import uzbspravka_service
from src.services.uzbspravka_service import (
    SHEET_NAMES,
    SHEET_SHORT,
    SHEETS,
    SheetNumbers,
    UzbSpravkaResult,
    UzbSpravkaService,
)


class UzbSpravkaController:
    def __init__(self, ocr: OcrService, service: UzbSpravkaService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    def can_make_qr(self) -> bool:
        return self._service.can_make_qr()

    # ------------------------------------------------------------- sheets
    @staticmethod
    def sheets() -> tuple[int, ...]:
        return SHEETS

    @staticmethod
    def sheet_names() -> dict[int, str]:
        return dict(SHEET_NAMES)

    @staticmethod
    def sheet_short() -> dict[int, str]:
        return dict(SHEET_SHORT)

    @staticmethod
    def blanks() -> dict[int, Path]:
        return uzbspravka_service.blanks()

    @staticmethod
    def set_blank(sheet: int, source: Path) -> Path:
        return uzbspravka_service.set_blank(sheet, source)

    @staticmethod
    def clear_blank(sheet: int) -> None:
        uzbspravka_service.clear_blank(sheet)

    # -------------------------------------------------------------- seals
    @staticmethod
    def seals() -> dict[str, Path]:
        return uzbspravka_service.seals()

    @staticmethod
    def add_seal(firm: str, source: Path) -> Path:
        return uzbspravka_service.add_seal(firm, source)

    @staticmethod
    def remove_seal(firm: str) -> None:
        uzbspravka_service.remove_seal(firm)

    # ------------------------------------------------------------- layout
    @staticmethod
    def layout() -> dict:
        return uzbspravka_service.load_layout()

    @staticmethod
    def save_layout(layout: dict) -> None:
        uzbspravka_service.save_layout(layout)

    # ------------------------------------------------------------ numbers
    @staticmethod
    def new_numbers(sheets=SHEETS) -> dict[int, SheetNumbers]:
        return uzbspravka_service.new_numbers(sheets)

    # ------------------------------------------------------------ reading
    def read_passport(self, image: bytes, *, firm: str) -> UzbData:
        """The worker off his passport — his rows, then his ПИНФЛ.

        Two requests, because they read two different parts of the page and
        each is judged on its own: a strip too blurred to read costs the
        ПИНФЛ box and nothing else.
        """
        passport = self._ocr.read_passport(image)
        pinfl = self._ocr.read_pinfl(image, passport.birth_date)
        return uzbspravka_service.data_of(passport, firm=firm, pinfl=pinfl)

    # ----------------------------------------------------------- printing
    def generate(self, data: UzbData, sheets=SHEETS, *,
                 numbers: dict[int, SheetNumbers] | None = None,
                 with_qr: bool = True) -> UzbSpravkaResult:
        return self._service.generate(data, sheets, numbers=numbers,
                                      with_qr=with_qr)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
