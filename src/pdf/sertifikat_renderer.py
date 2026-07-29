"""Fill a СЕРТИФИКАТ from the учебный центр's blank.

The blank is a two-page scan of the security paper. Page 1 — the guilloche
reverse — is copied through untouched, exactly as the office wants it; page 2
is the printed side and carries everything the operator typed. The result is
one PDF of two pages, which is what goes to the printer.

Three rules of this certificate that are easy to get wrong and are therefore
kept here rather than in the screen:

* **it runs three years to the day before.** From 10.07.2026 it ends
  09.07.2029 — the same shape of rule as the permit's year, one turn longer.
* **the name is written twice.** The first line is the passport's Cyrillic; the
  line under it is the same name in Latin, and — as on the passport itself —
  the patronymic is not carried into the Latin line.
* **both numbers re-roll their last three figures.** The registration number
  and the figures under the barcode each keep their block and change only their
  tail, so two certificates never leave the office with the same number on
  them. The bars themselves are printed on the paper and do not change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import fitz

from src.common.logging import get_logger
from src.pdf.engine import _font_file
from src.pdf.sertifikat_spec import (
    BARCODE_BARS,
    BARCODE_BASELINE,
    BARCODE_DIGITS,
    BARCODE_RED,
    BARCODE_SIZE,
    FIO_CYRILLIC,
    FIO_LATIN,
    FIO_MIN_SIZE,
    FIO_WIDTH,
    SANS,
    SANS_BOLD,
    VALUE_PAGE,
    VALUES,
    Slot,
)

log = get_logger(__name__)

#: The blank that ships with the program.
BUNDLED = Path("templates") / "sertifikat" / "standart"
#: The two halves of a blank, in the order they are printed.
PAGE_FILES = ("page1.pdf", "page2.pdf")

_FONT_KEYS = {"sc": SANS, "scb": SANS_BOLD}

#: ICAO Doc 9303 — the table Russian passports themselves are transliterated
#: with, so the Latin line on the certificate matches the Latin line on the
#: document the holder is carrying.
_LATIN = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E", "Ё": "E",
    "Ж": "ZH", "З": "Z", "И": "I", "Й": "I", "К": "K", "Л": "L", "М": "M",
    "Н": "N", "О": "O", "П": "P", "Р": "R", "С": "S", "Т": "T", "У": "U",
    "Ф": "F", "Х": "KH", "Ц": "TS", "Ч": "CH", "Ш": "SH", "Щ": "SHCH",
    "Ъ": "IE", "Ы": "Y", "Ь": "", "Э": "E", "Ю": "IU", "Я": "IA",
    # the letters the neighbours' passports add, folded onto their Russian twin
    # before the table is applied
    "Ҳ": "KH", "Қ": "K", "Ғ": "G", "Ӣ": "I", "Ӯ": "U", "Ҷ": "J", "Ӧ": "O",
    "Ө": "O", "Ң": "N", "Ү": "U", "Ұ": "U", "Һ": "KH", "Ә": "A", "І": "I",
    "Ї": "I", "Є": "E", "Ґ": "G",
}


@dataclass(frozen=True)
class SertifikatData:
    """Everything one certificate says."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    #: «Москва» or «Московская область»
    city: str = ""
    issued_on: date | None = None
    #: «002010264154» — as it will be printed, tail already rolled
    reg_number: str = ""
    #: the thirteen figures under the bars, tail already rolled
    barcode_number: str = ""


def valid_until(start: date) -> date:
    """Three years of validity end the day before the third anniversary."""
    try:
        anniversary = start.replace(year=start.year + 3)
    except ValueError:                       # issued on 29 February
        anniversary = date(start.year + 3, 3, 1)
    return anniversary - timedelta(days=1)


def to_latin(text: str) -> str:
    """«АЗИЗОВ НУСРАТУЛЛО» → «AZIZOV NUSRATULLO».

    Text already in Latin is handed back as it stands, so a passport that
    printed the name in Latin in the first place is not mangled a second time.
    """
    out = []
    for ch in (text or "").upper():
        out.append(_LATIN.get(ch, ch))
    return "".join(out)


def latin_line(surname: str, name: str) -> str:
    """The certificate's second line: surname and given name, no patronymic.

    The passport's own Latin line carries no patronymic either, and the office's
    filled certificate follows it — «АЗИЗОВ НУСРАТУЛЛО МЕЙЛИКОВИЧ» over
    «AZIZOV NUSRATULLO».
    """
    return " ".join(p for p in (to_latin(surname), to_latin(name)) if p).strip()


def cyrillic_line(surname: str, name: str, patronymic: str = "") -> str:
    """The certificate's first line: the whole name, as the passport spells it."""
    parts = [(p or "").strip().upper() for p in (surname, name, patronymic)]
    return " ".join(p for p in parts if p)


def roll_number(number: str, tail: int, digit: str) -> str:
    """Keep the block, replace the last ``tail`` figures with ``digit``.

    ``digit`` is passed in rather than drawn here so the caller owns the
    randomness — which keeps this function, and the tests over it, honest.
    """
    digits = "".join(c for c in (number or "") if c.isdigit())
    if len(digits) <= tail:
        return digits
    return digits[:-tail] + digit[:tail].rjust(tail, "0")


def _dmy(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _fonts(page) -> dict[str, str]:
    for handle, key in _FONT_KEYS.items():
        page.insert_font(fontname=handle, fontfile=str(_font_file(key)))
    return {key: handle for handle, key in _FONT_KEYS.items()}


def _centred(page, slot: Slot, text: str, fonts: dict[str, str],
             max_width: float = 0.0, min_size: float = 0.0) -> None:
    """Write ``text`` centred on ``slot``, shrinking it if it would not fit."""
    if not text:
        return
    size = slot.size
    font = fitz.Font(fontfile=str(_font_file(slot.font)))
    if max_width:
        while size > min_size and font.text_length(text, fontsize=size) > max_width:
            size -= 0.25
    width = font.text_length(text, fontsize=size)
    page.insert_text((slot.centre - width / 2, slot.baseline), text,
                     fontname=fonts[slot.font], fontsize=size, color=slot.colour)


def _barcode_digits(page, number: str, fonts: dict[str, str]) -> None:
    """The figures under the bars, one to a cell across the bars' own width.

    The bars are printed on the paper and cannot follow the number, so the
    figures are laid out to the width of the bars above them and no attempt is
    made to encode anything — this row is read by eye, not by a scanner.
    """
    digits = "".join(c for c in (number or "") if c.isdigit())
    if not digits:
        return
    digits = digits[-BARCODE_DIGITS:].rjust(BARCODE_DIGITS, "0")
    left, right = BARCODE_BARS[0], BARCODE_BARS[2]
    pitch = (right - left) / BARCODE_DIGITS
    font = fitz.Font(fontfile=str(_font_file(SANS_BOLD)))
    for i, digit in enumerate(digits):
        width = font.text_length(digit, fontsize=BARCODE_SIZE)
        x = left + pitch * (i + 0.5) - width / 2
        page.insert_text((x, BARCODE_BASELINE), digit,
                         fontname=fonts[SANS_BOLD], fontsize=BARCODE_SIZE,
                         color=BARCODE_RED)


def _blank_pages(template: Path | None) -> tuple[Path, Path]:
    folder = Path(template) if template else BUNDLED
    pages = tuple(folder / name for name in PAGE_FILES)
    for page in pages:
        if not page.exists():
            raise FileNotFoundError(page)
    return pages


def render(data: SertifikatData, template: Path | None = None) -> bytes:
    """The filled certificate as a two-page PDF: the reverse, then the face."""
    first, second = _blank_pages(template)
    out = fitz.open()
    out.insert_pdf(fitz.open(str(first)))
    out.insert_pdf(fitz.open(str(second)))
    if out.page_count <= VALUE_PAGE:
        raise ValueError("Сертификат бланкаси 2 саҳифа бўлиши керак")

    _fill(out[VALUE_PAGE], data)
    log.info("Сертификат: %s %s — рег %s / штрих %s",
             data.surname, data.name, data.reg_number, data.barcode_number)
    return out.tobytes()


def _fill(page, data: SertifikatData) -> None:
    fonts = _fonts(page)

    _centred(page, FIO_CYRILLIC,
             cyrillic_line(data.surname, data.name, data.patronymic),
             fonts, FIO_WIDTH, FIO_MIN_SIZE)
    _centred(page, FIO_LATIN, latin_line(data.surname, data.name),
             fonts, FIO_WIDTH, FIO_MIN_SIZE)

    until = valid_until(data.issued_on) if data.issued_on else None
    values = {
        "city": (data.city or "").strip(),
        "reg_number": (data.reg_number or "").strip(),
        "issued_on": _dmy(data.issued_on),
        "valid_until": _dmy(until),
    }
    for key, text in values.items():
        _centred(page, VALUES[key], text, fonts)

    _barcode_digits(page, data.barcode_number, fonts)
