"""Coordinates the registration use-case for the UI.

Holds no business logic: reads the documents via OCR and calls
RegistrationService. Mirrors :class:`ProcessController` but for the «Уведомление
о прибытии» form (address chosen instead of company; one extra input — the
registration expiry date).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.logging import get_logger
from src.domain.registration_address import RegistrationAddress
from src.ocr.service import OcrService
from src.services.registration_address_service import RegistrationAddressService
from src.services.registration_service import RegistrationResult, RegistrationService

log = get_logger(__name__)


class RegistrationController:
    def __init__(
        self,
        addresses: RegistrationAddressService,
        ocr: OcrService,
        registration: RegistrationService,
    ) -> None:
        self._addresses = addresses
        self._ocr = ocr
        self._registration = registration

    def addresses(self) -> list[RegistrationAddress]:
        """This section's OWN addresses — «regular» — and nobody else's.

        Хостел and МВД РЕГИСТРАЦИЯ each keep their addresses under their own
        kind and each shows only its own. This one asked for the lot, so a
        hostel added next door turned up in the РЕГИСТРАЦИЯ list on a blank
        that was never meant for it. The office said it plainly: «МВД
        регистрациялар фақат МВД бўлимда, хостел регистрациялар фақат
        хостел бўлимда».
        """
        return self._addresses.list(kind="regular")

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
    ) -> RegistrationResult:
        passport, patent = self._ocr.read_documents(
            passport_image, patent_image, patent_back_image
        )
        return self._registration.generate(
            passport, patent, address, registration_expiry=registration_expiry
        )

    @staticmethod
    def read_image(path: Path) -> bytes:
        return path.read_bytes()
