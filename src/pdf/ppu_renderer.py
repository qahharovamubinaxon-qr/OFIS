"""Fill the ППУ pair from the office's own blanks.

Two sheets — a front and a back. The values come off the регистрация the
operator drops in; the start date they type; the end date the регистрация
itself carries. The worker's photograph goes in the window on the front with
its background cut away and laid on at seven parts in ten, so the sheet's own
paper shows through it the way the office's cards look.

The blanks are pictures, so nothing is rewritten and nothing on them is
touched: every value is drawn at the fraction of the page
:mod:`src.pdf.ppu_spec` puts it at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import fitz

from src.common.logging import get_logger
from src.pdf.engine import _font_file
from src.pdf.ppu_spec import (
    BACK,
    FRONT,
    PHOTO_BOX,
    PHOTO_OPACITY,
    SANS,
    SANS_BOLD,
    Slot,
)

log = get_logger(__name__)

#: The two halves of a blank, in the order they are printed.
PAGE_FILES = ("front.pdf", "back.pdf")

_FONT_KEYS = {"pp": SANS, "ppb": SANS_BOLD}

#: ICAO Doc 9303, the table the passports themselves use.
_LATIN = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "ZH", "З": "Z", "И": "I", "Й": "I", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "KH", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SHCH",
    "Ъ": "IE", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "IU", "Я": "IA",
    "Ҳ": "KH", "Қ": "K", "Ғ": "G", "Ӣ": "I", "Ӯ": "U", "Ҷ": "J", "Ө": "O",
    "Ң": "N", "Ү": "U", "Ұ": "U", "Һ": "KH", "Ә": "A", "І": "I", "Ї": "I",
    "Є": "E", "Ґ": "G",
}


@dataclass(frozen=True)
class PpuData:
    """Everything one ППУ pair says."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    birth_date: date | None = None
    gender: str = ""
    citizenship: str = ""
    #: the passport as printed — «FA 1234567»
    document: str = ""
    address: str = ""
    valid_from: date | None = None
    valid_to: date | None = None
    #: «AL0531591» — the blank's own number, printed in five places
    number: str = ""
    photo: bytes | None = None


def title_case(text: str) -> str:
    """«АРУТЮНЯН АРТАК» → «Арутюнян Артак», hyphens counted as word breaks."""
    def one(word: str) -> str:
        return "-".join(p[:1].upper() + p[1:].lower() for p in word.split("-"))

    return " ".join(one(w) for w in (text or "").split())


def to_latin(text: str) -> str:
    """«Арутюнян Артак Пайлунович» → «Arutiunian Artak Pailunovich»."""
    out = []
    for ch in text or "":
        mapped = _LATIN.get(ch.upper())
        if mapped is None:
            out.append(ch)
        elif ch.islower():
            # «ю» inside a word is «iu», not «Iu» — a capital in the middle of
            # a surname is exactly the kind of thing an inspector notices
            out.append(mapped.lower())
        else:
            out.append(mapped)
    return "".join(out)


def full_name(surname: str, name: str, patronymic: str = "") -> str:
    parts = [title_case(p) for p in (surname, name, patronymic) if (p or "").strip()]
    return " ".join(parts)


def _dmy(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _fonts(page) -> dict[str, str]:
    for handle, key in _FONT_KEYS.items():
        page.insert_font(fontname=handle, fontfile=str(_font_file(key)))
    return {key: handle for handle, key in _FONT_KEYS.items()}


def _write(page, slot: Slot, text: str, fonts: dict[str, str]) -> None:
    """Draw ``text`` at the slot's fraction of this page, shrinking to fit."""
    if not text:
        return
    rect = page.rect
    size = slot.size * rect.height
    limit = slot.width * rect.width
    font = fitz.Font(fontfile=str(_font_file(slot.font)))
    while size > 4.0 and font.text_length(text, fontsize=size) > limit:
        size -= 0.4
    page.insert_text((slot.x * rect.width, slot.baseline * rect.height), text,
                     fontname=fonts[slot.font], fontsize=size, color=slot.colour)


def _place_photo(page, photo: bytes | None) -> None:
    """The worker in the window: background cut away, seven parts in ten."""
    if not photo:
        return
    rect = page.rect
    box = fitz.Rect(PHOTO_BOX[0] * rect.width, PHOTO_BOX[1] * rect.height,
                    PHOTO_BOX[2] * rect.width, PHOTO_BOX[3] * rect.height)
    aspect = (box.x1 - box.x0) / (box.y1 - box.y0)
    try:
        from src.services.photo_service import cutout_portrait

        stream = cutout_portrait(photo, aspect=aspect, opacity=PHOTO_OPACITY)
    except Exception as exc:                      # noqa: BLE001
        log.warning("ППУ: расм тайёрланмади (%s) — ўз ҳолича", exc)
        stream = photo
    if stream is None:
        stream = photo
    try:
        page.insert_image(box, stream=stream, keep_proportion=False, overlay=True)
    except (RuntimeError, ValueError) as exc:
        log.warning("ППУ: расм жойлашмади: %s", exc)


def _blanks(template: Path) -> tuple[Path, Path]:
    pages = tuple(Path(template) / name for name in PAGE_FILES)
    for page in pages:
        if not page.exists():
            raise FileNotFoundError(page)
    return pages


def render(data: PpuData, template: Path) -> bytes:
    """The filled pair as a two-page PDF: front, then back."""
    front_blank, back_blank = _blanks(template)
    out = fitz.open()
    out.insert_pdf(fitz.open(str(front_blank)))
    out.insert_pdf(fitz.open(str(back_blank)))

    _fill_front(out[0], data)
    _fill_back(out[1], data)
    log.info("ППУ: %s %s — №%s, %s — %s", data.surname, data.name, data.number,
             _dmy(data.valid_from), _dmy(data.valid_to))
    return out.tobytes()


def _fill_front(page, data: PpuData) -> None:
    fonts = _fonts(page)
    _place_photo(page, data.photo)
    cyrillic = full_name(data.surname, data.name, data.patronymic)
    latin = to_latin(cyrillic)
    citizenship = (data.citizenship or "").strip().upper()
    values = {
        "fio": cyrillic,
        "fio_latin": latin,
        "fio_latin_2": latin,
        "birth_date": _dmy(data.birth_date),
        "gender": (data.gender or "").strip(),
        "citizenship": citizenship,
        "citizenship_2": citizenship,
        "country": title_case(citizenship),
        "number": f"№{data.number}" if data.number else "",
    }
    for key, text in values.items():
        _write(page, FRONT[key], text, fonts)


def _fill_back(page, data: PpuData) -> None:
    fonts = _fonts(page)
    number = f"№{data.number}" if data.number else ""
    for key in ("number_1", "number_2", "number_3", "number_4"):
        _write(page, BACK[key], number, fonts)
    _write(page, BACK["date_from"], _dmy(data.valid_from), fonts)
    _write(page, BACK["date_to"], _dmy(data.valid_to), fonts)
    _write(page, BACK["address"], (data.address or "").strip(), fonts)


def pages_as_png(pdf: bytes, zoom: float = 3.0) -> list[bytes]:
    """The finished pair as pictures — which is how the office files them."""
    doc = fitz.open("pdf", pdf)
    out = []
    for page in doc:
        shot = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        out.append(shot.tobytes("png"))
    return out
