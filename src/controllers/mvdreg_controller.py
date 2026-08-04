"""Coordinates the МВД РЕГИСТРАЦИЯ use-case for the UI.

Mirrors :class:`HostelController` — same address book, its own kind, its own
blank and its own one-window arrangement (texts, fonts, colours, signature,
stamp).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

from src.common.logging import get_logger
from src.domain.registration_address import RegistrationAddress
from src.ocr.service import OcrService
from src.services import mvdreg_service
from src.services.mvdreg_service import MvdRegResult, MvdRegService
from src.services.registration_address_service import RegistrationAddressService

log = get_logger(__name__)


class MvdRegController:
    def __init__(self, addresses: RegistrationAddressService,
                 ocr: OcrService, service: MvdRegService) -> None:
        self._addresses = addresses
        self._ocr = ocr
        self._service = service

    def addresses(self) -> list[RegistrationAddress]:
        found = self._addresses.list(kind="mvdreg")
        mvdreg_service.refresh_templates(found)
        return found

    def add_address(self, address: RegistrationAddress,
                    template_source: Path | None) -> RegistrationAddress:
        return self._addresses.create_mvdreg(address, template_source)

    def archive_address(self, address_id: UUID) -> None:
        self._addresses.archive(address_id)

    def archived_addresses(self) -> list[RegistrationAddress]:
        return self._addresses.list_archived(kind="mvdreg")

    def restore_address(self, address_id: UUID) -> RegistrationAddress:
        return self._addresses.restore(address_id)

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- blank
    def blank(self) -> Path:
        return mvdreg_service.blank_path()

    def set_blank(self, source: Path) -> Path:
        return mvdreg_service.set_blank(source)

    # ------------------------------------------------------------ assets
    def set_signature(self, png: bytes) -> Path:
        return mvdreg_service.set_signature(png)

    def set_stamp(self, source: Path) -> Path:
        return mvdreg_service.set_stamp(source)

    def asset(self, name: str) -> Path | None:
        return mvdreg_service.asset(name)

    def clear_asset(self, name: str) -> None:
        mvdreg_service.clear_asset(name)

    # ---------------------------------------------------------- printing
    def generate_from_images(
        self,
        address: RegistrationAddress,
        passport_image: bytes,
        patent_image: bytes | None,
        patent_back_image: bytes | None = None,
        *,
        registration_expiry: date,
        registration_start: date | None = None,
    ) -> MvdRegResult:
        passport, patent = self._ocr.read_documents(
            passport_image, patent_image, patent_back_image)
        return self._service.generate(
            passport, patent, address,
            registration_expiry=registration_expiry,
            registration_start=registration_start)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
