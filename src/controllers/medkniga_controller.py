"""МЕД КНИЖКА — reading the worker's document and printing his four pages."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.ocr.service import OcrService
from src.pdf.medkniga_spec import DEFAULT_KIT, KITS
from src.services import medkniga_service
from src.services.medkniga_service import MedKnigaResult, MedKnigaService


def _passport_from_patent(patent):
    """A stand-in Passport carrying only the patent's Russian ФИО, so the check
    panel can show a patent-only med book the same way it shows a passport."""
    from src.domain.documents import Passport

    return Passport(
        surname=patent.holder_surname or "—",
        name=patent.holder_name or "—",
        patronymic=patent.holder_patronymic or None,
        nationality=patent.holder_citizenship or None,
        number="—",
    )


class MedKnigaController:
    def __init__(self, ocr: OcrService, service: MedKnigaService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # -------------------------------------------------------------- blanks
    @staticmethod
    def kits() -> dict[str, str]:
        return dict(KITS)

    @staticmethod
    def blanks(kit: str = DEFAULT_KIT) -> dict[int, Path]:
        return medkniga_service.blanks(kit)

    @staticmethod
    def set_blank(page: int, source: Path, kit: str = DEFAULT_KIT) -> Path:
        return medkniga_service.set_blank(page, source, kit)

    @staticmethod
    def clear_blank(page: int, kit: str = DEFAULT_KIT) -> None:
        medkniga_service.clear_blank(page, kit)

    # ---------------------------------------------------------------- seal
    @staticmethod
    def stamp() -> Path | None:
        return medkniga_service.stamp()

    @staticmethod
    def set_stamp(source: Path) -> Path:
        return medkniga_service.set_stamp(source)

    @staticmethod
    def clear_stamp() -> None:
        medkniga_service.clear_stamp()

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
    def read_document(self, document_image: bytes, *, is_patent: bool = False):
        """The worker's ФИО for the operator to check — off the passport, or,
        when only the patent was dropped, off the patent (a stand-in passport
        so the same check panel can show it)."""
        if is_patent:
            patent = self._ocr.read_patent(document_image)
            return _passport_from_patent(patent)
        passport, _patent = self._ocr.read_documents(document_image)
        return passport

    def print_document(
        self,
        passport,
        *,
        position: str,
        city: str,
        number: str,
        exam_date: date | None,
        photo_png: bytes | None = None,
        signature_png: bytes | None = None,
        kit: str = DEFAULT_KIT,
    ) -> MedKnigaResult:
        """The four pages, from the ФИО IN THE BOXES — not the raw reading."""
        data = medkniga_service.data_of(
            passport, None, position=position, city=city, number=number,
            exam_date=exam_date, photo_png=photo_png,
            signature_png=signature_png)
        return self._service.generate(data, kit)

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
        kit: str = DEFAULT_KIT,
    ) -> MedKnigaResult:
        """Read and print in one go — kept for callers with no screen."""
        passport = self.read_document(document_image, is_patent=is_patent)
        return self.print_document(
            passport, position=position, city=city, number=number,
            exam_date=exam_date, photo_png=photo_png,
            signature_png=signature_png, kit=kit)

    def generate(self, data, kit: str = DEFAULT_KIT) -> MedKnigaResult:
        return self._service.generate(data, kit)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
