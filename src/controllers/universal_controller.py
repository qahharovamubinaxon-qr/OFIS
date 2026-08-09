"""УНИВЕРСАЛ — the bridge between the screen and the office's blank library.

Thin on purpose. What a text can be, where a blank is kept and how a page is
printed all live in the service and the renderer, so the screen and the bot
can never come to two different ideas of what a form is.
"""

from __future__ import annotations

from pathlib import Path

from src.ocr.service import OcrService
from src.pdf.universal_fields import (
    PICTURES,
    Field,
    UniversalData,
    catalogue_with,
    custom_key,
    is_custom,
    label_of,
    samples_with,
)
from src.services import universal_service
from src.services.universal_service import UniversalResult, UniversalService


class UniversalController:
    def __init__(self, ocr: OcrService, service: UniversalService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------- the library
    @staticmethod
    def names() -> list[str]:
        return universal_service.names()

    @staticmethod
    def add(name: str, source: Path) -> str:
        return universal_service.add(name, source)

    @staticmethod
    def rename(name: str, into: str) -> str:
        return universal_service.rename(name, into)

    @staticmethod
    def remove(name: str) -> None:
        universal_service.remove(name)

    @staticmethod
    def blank_of(name: str) -> Path | None:
        return universal_service.blank_of(name)

    @staticmethod
    def pages(name: str) -> list[bytes]:
        return universal_service.pages(name)

    # --------------------------------------------------------- the texts
    @staticmethod
    def fields(name: str) -> list[Field]:
        return universal_service.fields(name)

    @staticmethod
    def save_fields(name: str, placed: list[Field]) -> None:
        universal_service.save_fields(name, placed)

    @staticmethod
    def wants(name: str) -> set[str]:
        """Only the keys this form actually prints — the screen shows these."""
        return universal_service.wants(name)

    @staticmethod
    def custom_keys(name: str) -> list[str]:
        return universal_service.custom_keys(name)

    @staticmethod
    def catalogue(keys) -> dict[str, str]:
        return catalogue_with(keys)

    @staticmethod
    def samples(keys) -> dict[str, str]:
        return samples_with(keys)

    @staticmethod
    def label_of(key: str) -> str:
        return label_of(key)

    @staticmethod
    def custom_key(name: str) -> str:
        return custom_key(name)

    @staticmethod
    def is_custom(key: str) -> bool:
        return is_custom(key)

    @staticmethod
    def pictures() -> tuple[str, ...]:
        return PICTURES

    # ------------------------------------------------------ the pictures
    @staticmethod
    def picture_of(name: str, which: str) -> Path | None:
        return universal_service.picture_of(name, which)

    @staticmethod
    def set_picture(name: str, which: str, source: Path) -> Path:
        return universal_service.set_picture(name, which, source)

    @staticmethod
    def clear_picture(name: str, which: str) -> None:
        universal_service.clear_picture(name, which)

    # ------------------------------------------------------- the reading
    def read(self, passport: bytes | None,
             patent: bytes | None = None) -> UniversalData:
        """Whatever was dropped, read. Both are optional."""
        read_passport = self._ocr.read_passport(passport) if passport else None
        read_patent = self._ocr.read_patent(patent) if patent else None
        return universal_service.data_of(read_passport, read_patent)

    @staticmethod
    def portrait(image: bytes) -> bytes | None:
        """The worker's face, cut the one way every section cuts it."""
        from src.services.photo_service import prepare_portrait

        return prepare_portrait(image, aspect=0.75)

    # -------------------------------------------------------- the making
    def generate(self, name: str, data: UniversalData) -> UniversalResult:
        return self._service.generate(name, data)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return Path(path).read_bytes()


__all__ = ["UniversalController"]
