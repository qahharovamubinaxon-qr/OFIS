"""АЛПИНИСТ — reading the documents and printing the climber's card.

The ФИО comes off the patent when one is given (Russian, ready for the
card) and off the passport otherwise — the same
:meth:`OcrService.read_documents` merge every other section leans on.
The worker's snapshot is cleaned to a white ground and cut 3×4 here,
in the working thread, so the view never blocks.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.domain.documents import Passport
from src.ocr.service import OcrService
from src.pdf.alpinist_renderer import AlpinistData, plus_three_years
from src.pdf.alpinist_spec import PHOTO_RATIO
from src.services.alpinist_service import AlpinistResult, AlpinistService
from src.services.photo_service import prepare_portrait

log = get_logger(__name__)


def _card_photo(photo: bytes) -> bytes:
    """The worker's snapshot through the ONE crop the office trusts.

    :func:`prepare_portrait` is the РАСМ-ФОТО/СФЕРА pipeline — YuNet face,
    eye-line straightening, head at the office's own share of the frame,
    U²-Net white ground — the owner asked АЛПИНИСТ cut exactly like that."""
    made = prepare_portrait(photo, aspect=PHOTO_RATIO)
    if made is None:
        raise OfisError("Ишчи расми ўқилмади — JPG ёки PNG расм ташланг.")
    return made


class AlpinistController:
    def __init__(self, ocr: OcrService, service: AlpinistService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- store
    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, source: Path) -> Path:
        return self._service.add_template(name, source)

    def remove_template(self, template: Path) -> None:
        self._service.remove_template(template)

    def stamp(self) -> Path | None:
        return self._service.stamp()

    def set_stamp(self, source: Path) -> Path:
        return self._service.set_stamp(source)

    def remove_stamp(self) -> None:
        self._service.remove_stamp()

    def layout(self, template: Path | None) -> dict:
        return self._service.layout(template)

    def save_layout(self, template: Path, layout: dict):
        return self._service.save_layout(template, layout)

    def next_number(self) -> int:
        return self._service.next_number()

    # ------------------------------------------------------------ reading
    def read_documents(self, passport_image: bytes,
                       patent_image: bytes | None) -> Passport:
        passport, _patent = self._ocr.read_documents(passport_image,
                                                     patent_image)
        return passport

    # ----------------------------------------------------------- printing
    def generate(self, *, template: Path | None, passport: Passport,
                 issue_date: date, ud_number: str, blank_number: str,
                 photo: bytes | None, signature: bytes | None) -> AlpinistResult:
        data = AlpinistData(
            surname=passport.surname or "",
            name=passport.name or "",
            patronymic=passport.patronymic or "",
            ud_number=ud_number, blank_number=blank_number,
            issue_date=issue_date,
            photo_png=_card_photo(photo) if photo else None,
            sign_png=signature)
        stamp = self._service.stamp()
        if stamp is not None:
            data.stamp_png = stamp.read_bytes()
        return self._service.generate(data, template)

    @staticmethod
    def until(issue_date: date | None) -> date | None:
        return plus_three_years(issue_date)
