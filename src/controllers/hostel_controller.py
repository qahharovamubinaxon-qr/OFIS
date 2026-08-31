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
from src.services.hostel_service import HostelResult, HostelService, StaySpot
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

    def archived_addresses(self) -> list[RegistrationAddress]:
        """Hostels removed from the picker — still recoverable."""
        return self._addresses.list_archived(kind="hostel")

    def restore_address(self, address_id: UUID) -> RegistrationAddress:
        return self._addresses.restore(address_id)

    def stay_from_spot(self, address: RegistrationAddress | None = None, *,
                       template: Path | None = None,
                       current: tuple[float, float] | None = None) -> StaySpot:
        """The page picture and the current spot of the stay-start date."""
        return self._hostel.stay_from_spot(address, template=template,
                                           current=current)

    def set_stay_from(self, address_id: UUID,
                      spot: tuple[float, float] | None) -> RegistrationAddress:
        """Save where this hostel wants it; ``None`` restores the form's own spot."""
        return self._addresses.set_stay_from(address_id, spot)

    def ai_available(self) -> bool:
        return self._ocr.available()

    def read_documents(
        self,
        passport_image: bytes,
        patent_image: bytes | None,
        patent_back_image: bytes | None = None,
    ):
        """What the passport and patent say — for the operator to check.

        The office asked for the ХОСТЕЛ notice to read on upload and show the
        values in fields, so a misread name is caught before it goes onto a
        filed «Уведомление о прибытии» — the same read-then-check flow as
        Регистрация.
        """
        return self._ocr.read_documents(
            passport_image, patent_image, patent_back_image
        )

    def generate(
        self,
        passport,
        patent,
        address: RegistrationAddress,
        *,
        registration_expiry: date,
        registration_start: date | None = None,
    ) -> HostelResult:
        """The document, from what is IN THE BOXES — not from what was read."""
        return self._hostel.generate(
            passport, patent, address,
            registration_expiry=registration_expiry,
            registration_start=registration_start,
        )

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
        """Read and print in one go — kept for the bot, which has no screen."""
        passport, patent = self.read_documents(
            passport_image, patent_image, patent_back_image
        )
        return self.generate(
            passport, patent, address,
            registration_expiry=registration_expiry,
            registration_start=registration_start,
        )

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
