"""КАРТА ИНОСТРАННОГО ГРАЖДАНИНА — blanks, running numbers, printing."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.karta_renderer import KartaData, output_name, render
from src.pdf.karta_spec import (
    FIRST_CARD_NO,
    FIRST_SERIAL,
    FIRST_SERIES,
    KEY_CARD_NO,
    KEY_SERIAL,
    KEY_SERIES,
)
from src.services import blank_layout

log = get_logger(__name__)

SECTION = "karta"
BLANK_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}
SIDES = ("inner", "outer")


def templates_dir() -> Path:
    folder = paths.user_templates_dir() / "karta"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@dataclass(frozen=True)
class KartaResult:
    pdf: bytes
    saved: Path
    surname: str
    card_number: str


class KartaService:
    def __init__(self, settings=None) -> None:
        self._settings = settings

    # ---------------------------------------------------------- templates
    def blank(self, side: str) -> Path | None:
        found = sorted(templates_dir().glob(f"{side}.*"))
        return found[0] if found else None

    def set_blank(self, side: str, source: Path) -> Path:
        if side not in SIDES:
            raise ValidationError("Томон нотўғри")
        source = Path(source)
        if source.suffix.lower() not in BLANK_SUFFIXES or not source.exists():
            raise ValidationError("Бланка PDF ёки расм бўлиши керак")
        for old in templates_dir().glob(f"{side}.*"):
            old.unlink(missing_ok=True)
        dest = templates_dir() / f"{side}{source.suffix.lower()}"
        shutil.copyfile(source, dest)
        log.info("КАРТА бланкаси янгиланди: %s", dest.name)
        return dest

    def remove_blank(self, side: str) -> None:
        for old in templates_dir().glob(f"{side}.*"):
            old.unlink(missing_ok=True)
            blank_layout.reset(SECTION, old)

    # ------------------------------------------------------------ layout
    def layout(self) -> dict:
        inner = self.blank("inner")
        return blank_layout.load(SECTION, inner) if inner else {}

    def save_layout(self, layout: dict):
        inner = self.blank("inner")
        if inner is None:
            raise ValidationError("Аввал ички бланкани юкланг.")
        kept = self.layout()
        return blank_layout.save(SECTION, inner, {**kept, **layout})

    # ---------------------------------------------------- running numbers
    def _next(self, key: str, first: int) -> int:
        if self._settings is None:
            return first
        raw = str(self._settings.get(key, "") or "").strip()
        return int(raw) if raw.isdigit() else first

    def next_numbers(self) -> dict[str, str]:
        """What the NEXT card takes — shown in the view before printing."""
        return {
            "serial": str(self._next(KEY_SERIAL, FIRST_SERIAL)),
            "card_number": str(self._next(KEY_CARD_NO, FIRST_CARD_NO)),
            "series": f"{self._next(KEY_SERIES, FIRST_SERIES):04d}",
        }

    def _advance(self) -> None:
        if self._settings is None:
            return
        for key, first in ((KEY_SERIAL, FIRST_SERIAL),
                           (KEY_CARD_NO, FIRST_CARD_NO),
                           (KEY_SERIES, FIRST_SERIES)):
            self._settings.set(key, str(self._next(key, first) + 1))

    # ---------------------------------------------------------- printing
    def generate(self, data: KartaData) -> KartaResult:
        inner = self.blank("inner")
        if inner is None:
            raise ValidationError(
                "Картанинг ички бланкаси юкланмаган — «➕ Ички» билан юкланг.")
        if not (data.surname or "").strip():
            raise ValidationError("Фамилия керак — паспортни ўқитинг")
        numbers = self.next_numbers()
        data.serial = data.serial or numbers["serial"]
        data.card_number = data.card_number or numbers["card_number"]
        data.series = data.series or numbers["series"]
        data.layout = self.layout()
        pdf = render(data, inner, self.blank("outer"))

        folder = paths.output_dir() / "karta"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / output_name(data)
        counter = 2
        while target.exists():
            target = folder / f"{target.stem.split(' (')[0]} ({counter}).pdf"
            counter += 1
        target.write_bytes(pdf)
        self._advance()
        log.info("КАРТА: %s — %s (№ %s)", data.fio(), target.name,
                 data.card_number)
        return KartaResult(pdf=pdf, saved=target,
                           surname=(data.surname or "").strip(),
                           card_number=data.card_number)
