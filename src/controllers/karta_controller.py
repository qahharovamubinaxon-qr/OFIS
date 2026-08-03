"""КАРТА ИНОСТРАННОГО ГРАЖДАНИНА — the passport in, the card out."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.domain.documents import Passport
from src.ocr.service import OcrService
from src.pdf.karta_renderer import KartaData, plus_years
from src.pdf.karta_spec import PHOTO_BOX
from src.services.karta_service import KartaResult, KartaService
from src.services.photo_service import prepare_portrait

log = get_logger(__name__)


def _card_photo(image: bytes) -> bytes:
    """The worker's snapshot through the ONE crop, at the frame's shape."""
    x0, y0, x1, y1 = PHOTO_BOX
    # the blank is 1683×1058 pt — the frame's real aspect follows from that
    aspect = ((x1 - x0) * 1683) / ((y1 - y0) * 1058)
    made = prepare_portrait(image, aspect=aspect)
    if made is None:
        raise OfisError("Ишчи расми ўқилмади — JPG ёки PNG ташланг.")
    return made


class KartaController:
    def __init__(self, ocr: OcrService, service: KartaService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- store
    def blank(self, side: str) -> Path | None:
        return self._service.blank(side)

    def set_blank(self, side: str, source: Path) -> Path:
        return self._service.set_blank(side, source)

    def remove_blank(self, side: str) -> None:
        self._service.remove_blank(side)

    def layout(self) -> dict:
        return self._service.layout()

    def save_layout(self, layout: dict):
        return self._service.save_layout(layout)

    def next_numbers(self) -> dict[str, str]:
        return self._service.next_numbers()

    # ------------------------------------------------------------ reading
    def read_passport(self, image: bytes) -> Passport:
        return self._ocr.read_passport(image)

    @staticmethod
    def expiry(issued: date | None) -> date | None:
        return plus_years(issued)

    # ----------------------------------------------------------- printing
    def generate(self, *, passport: Passport, photo: bytes,
                 signature: bytes | None, issued: date,
                 card_code: str) -> KartaResult:
        data = KartaData(
            surname=passport.surname or "",
            name=passport.name or "",
            patronymic=passport.patronymic or "",
            gender=(passport.gender.value
                    if getattr(passport.gender, "value", None)
                    else str(passport.gender or "")),
            citizenship=passport.nationality or "",
            birth_date=passport.birth_date,
            issued=issued, expiry=plus_years(issued),
            card_code=card_code,
            photo_png=_card_photo(photo), sign_png=signature)
        return self._service.generate(data)
