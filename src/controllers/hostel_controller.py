"""Coordinates the ХОСТЕЛ use-case for the UI.

Mirrors :class:`RegistrationController` but lists only hostel addresses and
fills via :class:`HostelService` (the hostel form's own coordinate map).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

from src.common.logging import get_logger
from src.domain.registration_address import RegistrationAddress
from src.ocr.service import OcrService
from src.services.hostel_service import HostelResult, HostelService
from src.services.registration_address_service import RegistrationAddressService

log = get_logger(__name__)


class HostelController:
    def __init__(
        self,
        addresses: RegistrationAddressService,
        ocr: OcrService,
        hostel: HostelService,
    ) -> None:
        self._addresses = addresses
        self._ocr = ocr
        self._hostel = hostel

    def addresses(self) -> list[RegistrationAddress]:
        return self._addresses.list(kind="hostel")

    def add_address(
        self, address: RegistrationAddress, template_source: Path | None
    ) -> RegistrationAddress:
        return self._addresses.create_hostel(address, template_source)

    def archive_address(self, address_id: UUID) -> None:
        self._addresses.archive(address_id)

    def ai_available(self) -> bool:
        return self._ocr.available()

    def generate_from_images(
        self,
        address: RegistrationAddress,
        passport_image: bytes,
        patent_image: bytes | None,
        patent_back_image: bytes | None = None,
        *,
        registration_expiry: date,
        registration_start: date | None = None,
    ) -> HostelResult:
        passport, patent = self._ocr.read_documents(
            passport_image, patent_image, patent_back_image
        )
        return self._hostel.generate(
            passport, patent, address,
            registration_expiry=registration_expiry,
            registration_start=registration_start,
        )

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
