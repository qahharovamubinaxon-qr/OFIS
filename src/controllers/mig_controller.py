"""МИГ controller — one passport in, the card's own fields out.

The card carries the worker's name, birth date, citizenship, sex and passport
number, and nothing else about him. Everything the reader hands back stays
editable on screen: a passport photographed at an angle is ordinary, and a wrong
name on a printed card is not.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.common.logging import get_logger
from src.controllers.trud_ppu_controller import gender_from_patronymic
from src.domain.documents import Passport
from src.domain.passport_rules import series_in_latin
from src.ocr.service import OcrService
from src.services.mig_service import MigResult, MigService, Stamp

log = get_logger(__name__)


class MigController:
    def __init__(self, ocr: OcrService, service: MigService) -> None:
        self._ocr = ocr
        self._service = service

    # ------------------------------------------------------------- state
    def ai_available(self) -> bool:
        return self._ocr.available()

    def templates(self) -> list[Path]:
        return self._service.templates()

    def add_template(self, name: str, source: Path) -> Path:
        return self._service.add_template(name, source)

    def remove_template(self, template: Path) -> None:
        self._service.remove_template(template)

    def layout(self, template: Path | None) -> dict:
        return self._service.layout(template)

    def save_layout(self, template: Path, layout: dict):
        return self._service.save_layout(template, layout)

    def reset_layout(self, template: Path) -> None:
        self._service.reset_layout(template)

    def stamps(self) -> list[Stamp]:
        return self._service.stamps()

    def add_stamp(self, name: str, source: Path) -> Stamp:
        return self._service.add_stamp(name, source)

    def place_stamp(self, stamp, box) -> None:
        self._service.place_stamp(stamp, box)

    def remove_stamp(self, stamp) -> None:
        self._service.remove_stamp(stamp)

    # ---------------------------------------------------------- passport
    def read_passport(self, image: bytes) -> dict[str, str]:
        """The six fields the card takes off a passport."""
        passport: Passport = self._ocr.read_passport(image)
        return {
            "surname": (passport.surname or "").strip(),
            "name": (passport.name or "").strip(),
            "patronymic": (passport.patronymic or "").strip(),
            "birth_date": (passport.birth_date.strftime("%d.%m.%Y")
                           if passport.birth_date else ""),
            "citizenship": (passport.nationality or "").strip(),
            "gender": card_gender(passport),
            "passport": passport_line(passport),
        }

    # ---------------------------------------------------------- printing
    def generate(self, **kwargs) -> MigResult:
        return self._service.generate(**kwargs)

    @staticmethod
    def read_image(path: Path) -> bytes:
        return Path(path).read_bytes()

    @staticmethod
    def parse_date(text: str) -> date | None:
        text = (text or "").strip()
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None


def passport_line(passport: Passport) -> str:
    """«FB» + «2376204» → «FB2376204», as the card prints it.

    The series is put into LATIN letters first: a passport series is never
    translated, and a reader that hands «ФБ» back would put Cyrillic on a card
    whose other letters are Latin. A Tajik passport has no series at all — nine
    digits beginning with 4 — and then there is only the number.
    """
    series = series_in_latin(passport.series or "")
    number = "".join((passport.number or "").split())
    return f"{series}{number}".strip()


#: The card says «Мужской» / «Женский»; the reader says «male» / «female».
_GENDER_WORD = {"male": "Мужской", "female": "Женский"}


def card_gender(passport: Passport) -> str:
    """Which box the X goes in, as the card spells it.

    The reader hands sex back as :class:`Gender` — «male» / «female» — and the
    card's own words are «Мужской» / «Женский»; without translating, the screen
    matched nothing and the operator had to pick it by hand every time.

    A passport photographed badly often loses it altogether. The patronymic then
    says it without asking anyone: «…овна» is a woman, «…ович» and «…ўғли» a man.
    """
    word = _GENDER_WORD.get(
        str(passport.gender.value).lower() if passport.gender else "", "")
    return word or gender_from_patronymic(passport.patronymic or "")
