"""АЛЬЯНСКОТ 2400 — reading the passport and printing the three papers.

The ФИО comes off the patent when one is given (Russian, ready for the card)
and off the passport otherwise — the same :meth:`OcrService.read_documents`
merge every other section leans on. The worker's snapshot is cleaned to a
white ground and cut 3×4 here, in the working thread, so the view never
blocks. The signature arrives already drawn in ink from the signature pad.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.domain.documents import Passport
from src.ocr.service import OcrService
from src.pdf.alliance_renderer import AllianceData, end_date
from src.pdf.alpinist_spec import PHOTO_RATIO
from src.services.alliance_service import AllianceResult, AllianceService
from src.services.photo_service import prepare_portrait

log = get_logger(__name__)


def _card_photo(photo: bytes) -> bytes:
    """The worker's snapshot through the ONE crop the office trusts —
    :func:`prepare_portrait` (YuNet face, eye-line straightening, U²-Net
    white ground), cut to the card's 3×4 frame."""
    made = prepare_portrait(photo, aspect=PHOTO_RATIO)
    if made is None:
        raise OfisError("Ишчи расми ўқилмади — JPG ёки PNG расм ташланг.")
    return made


class AllianceController:
    def __init__(self, ocr: OcrService, service: AllianceService) -> None:
        self._ocr = ocr
        self._service = service

    def ai_available(self) -> bool:
        return self._ocr.available()

    # ------------------------------------------------------------- blanks
    def set_blank(self, slot: str, source: Path) -> Path:
        return self._service.set_blank(slot, source)

    def blank(self, slot: str) -> Path | None:
        return self._service.blank(slot)

    def pages(self, slot: str) -> int:
        return self._service.pages(slot)

    def layout(self, slot: str) -> dict:
        return self._service.layout(slot)

    def save_layout(self, slot: str, layout: dict) -> None:
        self._service.save_layout(slot, layout)

    # ------------------------------------------------------------ reading
    @staticmethod
    def read_image(path: Path) -> bytes:
        """The dropped file's bytes (read on the UI thread, then handed to
        :meth:`read_documents` on a worker). Its absence is the exact bug
        that broke ТРУД — it must always be here."""
        return Path(path).read_bytes()

    def read_documents(self, passport_image: bytes,
                       patent_image: bytes | None = None) -> Passport:
        passport, _patent = self._ocr.read_documents(passport_image,
                                                     patent_image)
        return passport

    # ----------------------------------------------------------- printing
    def generate(self, *, passport: Passport, ud_number: str,
                 dolzhnost: str, gender: str, start_date: date,
                 photo: bytes | None, signature: bytes | None,
                 out_dir: Path | None = None) -> list[AllianceResult]:
        data = AllianceData(
            surname=passport.surname or "",
            name=passport.name or "",
            patronymic=passport.patronymic or "",
            gender=gender,
            ud_number=ud_number,
            dolzhnost=dolzhnost,
            start_date=start_date,
            photo_png=_card_photo(photo) if photo else None,
            sign_png=signature)
        return self._service.generate(data, out_dir)

    @staticmethod
    def until(start: date | None) -> date | None:
        return end_date(start)
