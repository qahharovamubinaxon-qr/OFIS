"""Fill the СНИЛС sheet — «Ишчининг СНИЛС номери» — from the office's blank.

The worker's passport gives the name, the birth date, the country they were
born in and their sex; the operator types the registration date and, when it is
not the one already standing there, the СНИЛС number itself.

The sheet writes its dates the way the form does — «"25" июня 1997», the day in
quotation marks and the month spelled out in the genitive — which is not what
any date formatter produces, so it is done here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

from src.common.logging import get_logger
from src.pdf.engine import _font_file
from src.pdf.snils_spec import (
    COVER_RIGHT,
    SANS,
    SANS_BOLD,
    SLOTS,
    VALUE_CAP,
    Slot,
)

log = get_logger(__name__)

BLANK_FILE = "blank.pdf"

_FONT_KEYS = {"sn": SANS, "snb": SANS_BOLD}

#: The genitive, because the form reads «"25" ИЮНЯ 1997» — «of June», not
#: «June». Every Russian form dates itself this way.
_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря")


@dataclass(frozen=True)
class SnilsData:
    """Everything one СНИЛС sheet says."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    birth_date: date | None = None
    #: the COUNTRY, as the form wants it — «КИРГИЗИЯ», not a town
    birth_place: str = ""
    gender: str = ""
    reg_date: date | None = None
    snils: str = ""


def form_date(value: date | None) -> str:
    """«"25" июня 1997» — the day quoted, the month spelled out."""
    if value is None:
        return ""
    return f'"{value.day:02d}" {_MONTHS[value.month - 1]} {value.year}'


def gender_word(gender: str) -> str:
    """«male» / «М» / «Мужской» → «МУЖСКОЙ», however it reached us."""
    text = (gender or "").strip().lower()
    if not text:
        return ""
    if text.startswith(("ж", "f", "w")) or "жен" in text:
        return "ЖЕНСКИЙ"
    if text.startswith(("м", "m")) or "муж" in text:
        return "МУЖСКОЙ"
    return text.upper()


def format_snils(number: str) -> str:
    """«22390231633» → «223-902-316 33», the shape the form prints.

    Anything that is not eleven digits is handed back as the operator typed
    it: they may be copying a number that is punctuated some other way, and
    silently reshaping a number nobody can check is worse than leaving it.
    """
    digits = "".join(c for c in (number or "") if c.isdigit())
    if len(digits) != 11:
        return (number or "").strip()
    return f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]} {digits[9:11]}"


def _fonts(page) -> dict[str, str]:
    for handle, key in _FONT_KEYS.items():
        page.insert_font(fontname=handle, fontfile=str(_font_file(key)))
    return {key: handle for handle, key in _FONT_KEYS.items()}


def _cover(page, slot: Slot) -> None:
    """White out whatever is already on this line, short of its rule."""
    page.draw_rect(fitz.Rect(slot.x - 8, slot.baseline - VALUE_CAP - 14,
                             COVER_RIGHT, slot.baseline + 6),
                   color=None, fill=(1, 1, 1))


def _write(page, slot: Slot, text: str, fonts: dict[str, str]) -> None:
    _cover(page, slot)
    if not text:
        return
    page.insert_text((slot.x, slot.baseline), text, fontname=fonts[slot.font],
                     fontsize=slot.size, color=slot.colour)


def render(data: SnilsData, template: Path) -> bytes:
    """The filled sheet as a one-page PDF."""
    blank = Path(template) / BLANK_FILE
    if not blank.exists():
        raise FileNotFoundError(blank)
    out = fitz.open()
    out.insert_pdf(fitz.open(str(blank)))
    page = out[0]
    fonts = _fonts(page)

    values = {
        "snils": format_snils(data.snils),
        "surname": (data.surname or "").strip().upper(),
        "name": (data.name or "").strip().upper(),
        "patronymic": (data.patronymic or "").strip().upper(),
        "birth_date": form_date(data.birth_date),
        "birth_place": (data.birth_place or "").strip().upper(),
        "gender": gender_word(data.gender),
        "reg_date": form_date(data.reg_date),
    }
    for key, text in values.items():
        _write(page, SLOTS[key], text, fonts)

    log.info("СНИЛС: %s %s — %s", data.surname, data.name, values["snils"])
    return out.tobytes()
