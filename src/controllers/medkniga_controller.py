"""МЕД КНИЖКА — reading the worker's document and printing his four pages."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.ocr.service import OcrService
from src.services import medkniga_service
from src.services.medkniga_service import MedKnigaResult, MedKnigaService


class MedKnigaController:
    def __init__(self, ocr: OcrService, service: MedKnigaService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # -------------------------------------------------------------- blanks
    @staticmethod
    def blanks() -> dict[int, Path]:
        return medkniga_service.blanks()

    @staticmethod
    def set_blank(page: int, source: Path) -> Path:
        return medkniga_service.set_blank(page, source)

    @staticmethod
    def clear_blank(page: int) -> None:
        medkniga_service.clear_blank(page)

    # -------------------------------------------------------------- layout
    @staticmethod
    def layout() -> dict:
        return medkniga_service.load_layout()

    @staticmethod
    def save_layout(layout: dict) -> None:
        medkniga_service.save_layout(layout)

    # -------------------------------------------------------------- number
    @staticmethod
    def next_number() -> str:
        return medkniga_service.next_number()

    # ------------------------------------------------------------ printing
    def generate_from_images(
        self,
        document_image: bytes,
        *,
        position: str,
        city: str,
        number: str,
        exam_date: date | None,
        photo_png: bytes | None = None,
        signature_png: bytes | None = None,
        is_patent: bool = False,
    ) -> MedKnigaResult:
        """Read the passport (or the patent) and print the four pages."""
        if is_patent:
            patent = self._ocr.read_patent(document_image)
            passport = None
        else:
            passport, patent = self._ocr.read_documents(document_image)
        data = medkniga_service.data_of(
            passport, patent, position=position, city=city, number=number,
            exam_date=exam_date, photo_png=photo_png,
            signature_png=signature_png)
        return self._service.generate(data)

    def generate(self, data) -> MedKnigaResult:
        return self._service.generate(data)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
