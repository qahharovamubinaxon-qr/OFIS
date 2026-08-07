"""АМИНА — the bridge between the screen and the office's own importer.

Nothing here decides anything: the rules for the login, the password and the
sheet all live in the service, so the screen and the bot cannot drift into two
different ideas of what a worker's account is.
"""

from __future__ import annotations

from pathlib import Path

from src.ocr.service import OcrService
from src.services import amina_service
from src.services.amina_service import (
    DOC_NAMES,
    DOCS,
    AminaData,
    AminaResult,
    AminaService,
)


class AminaController:
    def __init__(self, ocr: OcrService, service: AminaService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ----------------------------------------------------------- documents
    @staticmethod
    def docs() -> tuple[str, ...]:
        return DOCS

    @staticmethod
    def doc_names() -> dict[str, str]:
        return dict(DOC_NAMES)

    @staticmethod
    def doc_limit(key: str) -> int:
        return amina_service.doc_limit(key)

    # -------------------------------------------------------- the machinery
    def folder(self) -> Path:
        return amina_service.folder(self._service.settings)

    def check(self) -> None:
        """Whatever is missing, said before any work is done."""
        amina_service.check_folder(self._service.settings)

    def excel_is_open(self) -> bool:
        return amina_service.excel_is_open(self._service.settings)

    def excel(self) -> dict[str, str]:
        """What the Excel holds right now — for showing what was written."""
        return amina_service.read_excel(
            amina_service.excel_path(self._service.settings))

    # ---------------------------------------------------------- the rules
    @staticmethod
    def password_of(phone: str) -> str:
        return amina_service.password_of(phone)

    @staticmethod
    def email_of(surname: str, phone: str) -> str:
        return amina_service.email_of(surname, phone)

    # -------------------------------------------------------- what is typed
    @staticmethod
    def typed() -> dict[str, str]:
        return amina_service.typed()

    @staticmethod
    def remember_typed(**boxes: str) -> None:
        amina_service.remember_typed(**boxes)

    # ------------------------------------------------------------- reading
    def read_passport(self, image: bytes) -> AminaData:
        return amina_service.data_of(self._ocr.read_passport(image))

    # -------------------------------------------------------------- making
    def create(self, data: AminaData,
               images: dict[str, list[bytes]] | None = None,
               *, run: bool = True) -> AminaResult:
        return self._service.create(data, images, run=run)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()


__all__ = ["AminaController"]
