"""Fill a РАЗРЕШЕНИЕ card — front and back — from the office's blank pair.

The blanks are pictures of the real card, so nothing on them is searchable and
nothing is rewritten: every value is drawn at the point
:mod:`src.pdf.razreshenie_spec` measured it off the office's own filled card.
The card's own printing is never touched.

Two rules of the card that are easy to get wrong and are therefore kept here
rather than in the screen:

* **cover runs a year to the day before.** From 10.07.2026 it ends 09.07.2027 —
  the same rule as ОСАГО. The operator types the start; the end follows.
* **the ИНН rides with the passport.** «Документ удост. личность / ИНН» is one
  field: with an ИНН it reads «A2311191 / 772365215425», without one it is just
  the passport, exactly as the blank has it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import fitz

from src.common.logging import get_logger
from src.pdf.engine import _font_file
from src.pdf.razreshenie_spec import (
    BACK,
    FIRM_LINES,
    FIRM_MAX_WIDTH,
    FIRM_MIN_SIZE,
    FIRM_WIDTH,
    FRONT,
    NUMBER_BASELINE,
    NUMBER_DIGITS,
    NUMBER_PITCH,
    NUMBER_SIZE,
    NUMBER_X,
    PHOTO_BOX,
    PHOTO_OPACITY,
    SANS,
    SANS_BOLD,
    SERIF_BOLD,
    Slot,
)

log = get_logger(__name__)

#: The blanks that ship with the program.
BUNDLED = Path("templates") / "razreshenie" / "standart"

_FONT_KEYS = {"rz": SANS, "rzb": SANS_BOLD, "rzs": SERIF_BOLD}


@dataclass(frozen=True)
class RazreshenieData:
    """Everything one card says."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    birth_date: date | None = None
    citizenship: str = ""
    #: the passport as printed — «A2311191»
    document: str = ""
    #: the worker's ИНН; empty leaves the passport standing alone
    inn: str = ""
    activity: str = ""
    valid_from: date | None = None
    firm_name: str = ""
    firm_inn: str = ""
    #: «Серия 77 № 1354593»
    seria: str = "77"
    number: str = ""
    #: the seven digits behind «ВВ» on the back
    back_number: str = ""
    photo: bytes | None = None


def cover_until(start: date) -> date:
    """A year of cover ends the day before the anniversary."""
    try:
        anniversary = start.replace(year=start.year + 1)
    except ValueError:                       # taken out on 29 February
        anniversary = date(start.year + 1, 3, 1)
    return anniversary - timedelta(days=1)


def document_line(document: str, inn: str) -> str:
    """«A2311191 / 772365215425» — or just the passport when no ИНН was given."""
    document, inn = document.strip(), inn.strip()
    return f"{document} / {inn}" if document and inn else (document or inn)


def _dmy(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _wrap(text: str, font: fitz.Font, size: float, width: float) -> list[str]:
    """Break a firm's name the way the card does — on words, never mid-word."""
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        if line and font.text_length(trial, fontsize=size) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def _write(page, slot: Slot, text: str, fonts: dict[str, str]) -> None:
    if not text:
        return
    page.insert_text((slot.x, slot.baseline), text,
                     fontname=fonts[slot.font], fontsize=slot.size,
                     color=slot.colour)


def _cover_crop(photo: bytes, aspect: float) -> bytes:
    """Trim a photograph to the window's shape, from the middle."""
    from io import BytesIO

    from PIL import Image

    image = Image.open(BytesIO(photo))
    width, height = image.size
    if not width or not height:
        return photo
    if width / height > aspect:                   # too wide — trim the sides
        new = int(round(height * aspect))
        box = ((width - new) // 2, 0, (width - new) // 2 + new, height)
    else:                                         # too tall — trim from below
        new = int(round(width / aspect))
        box = (0, 0, width, min(new, height))
    out = BytesIO()
    image.convert("RGB").crop(box).save(out, format="PNG")
    return out.getvalue()


def _soften(photo: bytes, opacity: float) -> bytes:
    """Lay the photograph on at ``opacity``, letting the card show through.

    Done by giving the picture an alpha channel rather than by mixing it with a
    colour: what shows through is then whatever the blank actually has under
    the window, so this keeps working if the office changes the card's green.
    """
    from io import BytesIO

    from PIL import Image

    image = Image.open(BytesIO(photo)).convert("RGBA")
    image.putalpha(int(round(max(0.0, min(1.0, opacity)) * 255)))
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _place_photo(page, photo: bytes | None) -> None:
    """Fill the card's photo window edge to edge, at nine parts in ten.

    The window is 3 : 4 and the portrait is fitted to 3 : 4 first, so nothing is
    stretched; ``keep_proportion=False`` then guarantees no green shows through
    at the *edges*. Through the picture itself a tenth of the card does show —
    :data:`PHOTO_OPACITY` — which is how the office's own cards look.
    """
    if not photo:
        return
    aspect = (PHOTO_BOX[2] - PHOTO_BOX[0]) / (PHOTO_BOX[3] - PHOTO_BOX[1])
    stream = None
    try:
        from src.services.photo_service import prepare_portrait

        stream = prepare_portrait(photo, aspect=aspect, height=900)
    except Exception as exc:                      # noqa: BLE001
        log.warning("Разрешение: расм мослаштирилмади (%s)", exc)
    if stream is None:
        # the last line of defence for «рамкага 100 фоиз тўлиқ»: the picture
        # reaching the card is already the window's shape, so filling it edge
        # to edge cannot stretch a face
        try:
            stream = _cover_crop(photo, aspect)
        except Exception as exc:                  # noqa: BLE001
            log.warning("Разрешение: расм қирқилмади (%s) — ўз ҳолича", exc)
            stream = photo
    if PHOTO_OPACITY < 1.0:
        try:
            stream = _soften(stream, PHOTO_OPACITY)
        except Exception as exc:                  # noqa: BLE001
            log.warning("Разрешение: расм хиралаштирилмади (%s)", exc)
    try:
        page.insert_image(fitz.Rect(*PHOTO_BOX), stream=stream,
                          keep_proportion=False, overlay=True)
    except (RuntimeError, ValueError) as exc:
        log.warning("Разрешение: расм жойлашмади: %s", exc)


def _fonts(page) -> dict[str, str]:
    """Embed the card's faces once per page and hand back their handles."""
    for handle, key in _FONT_KEYS.items():
        page.insert_font(fontname=handle, fontfile=str(_font_file(key)))
    return {key: handle for handle, key in _FONT_KEYS.items()}


def render(data: RazreshenieData, template: Path | None = None) -> bytes:
    """The filled card as a two-page PDF: front, then back."""
    folder = Path(template) if template else BUNDLED
    front_blank, back_blank = folder / "front.pdf", folder / "back.pdf"
    for blank in (front_blank, back_blank):
        if not blank.exists():
            raise FileNotFoundError(blank)

    out = fitz.open()
    out.insert_pdf(fitz.open(str(front_blank)))
    out.insert_pdf(fitz.open(str(back_blank)))

    _fill_front(out[0], data)
    _fill_back(out[1], data)
    return out.tobytes()


def _fill_front(page, data: RazreshenieData) -> None:
    fonts = _fonts(page)
    _place_photo(page, data.photo)
    values = {
        "seria": data.seria.strip(),
        "number": data.number.strip(),
        "surname": data.surname.strip(),
        "name": data.name.strip(),
        "patronymic": data.patronymic.strip(),
        "birth_date": _dmy(data.birth_date),
        "citizenship": data.citizenship.strip(),
        "document": document_line(data.document, data.inn),
        "activity": data.activity.strip(),
        "valid_from": _dmy(data.valid_from),
        "valid_to": _dmy(cover_until(data.valid_from)) if data.valid_from else "",
    }
    for key, text in values.items():
        _write(page, FRONT[key], text, fonts)


def _firm_lines(name: str, slot: Slot) -> tuple[list[str], float]:
    """The firm's name over the card's two lines, and the size it took.

    At the printed size it wraps where the card wraps it. A name too long for
    that first spreads into the green the card leaves to its right, and only
    then is set smaller — anything rather than printing a firm half-named,
    because «ООО …» without the «…» is not a firm anybody can look up.
    """
    font = fitz.Font(fontfile=str(_font_file(slot.font)))
    size = slot.size
    while size >= FIRM_MIN_SIZE:
        for width in (FIRM_WIDTH, FIRM_MAX_WIDTH):
            lines = _wrap(name, font, size, width)
            if len(lines) <= FIRM_LINES:
                return lines, size
        size -= 0.4
    lines = _wrap(name, font, FIRM_MIN_SIZE, FIRM_MAX_WIDTH)
    log.warning("Разрешение: фирма номи 2 қаторга сиғмади — %s", name[:60])
    return lines[:FIRM_LINES], FIRM_MIN_SIZE


def _fill_back(page, data: RazreshenieData) -> None:
    fonts = _fonts(page)
    slot = BACK["firm_1"]
    lines, size = _firm_lines(data.firm_name.strip(), slot)
    for key, text in zip(("firm_1", "firm_2"), lines + [""], strict=False):
        _write(page, BACK[key]._replace(size=size), text, fonts)
    if data.firm_inn.strip():
        _write(page, BACK["firm_inn"], f"ИНН {data.firm_inn.strip()}", fonts)
    _write(page, BACK["issued_on"], _dmy(data.valid_from), fonts)

    digits = "".join(c for c in data.back_number if c.isdigit())
    digits = digits[-NUMBER_DIGITS:].rjust(NUMBER_DIGITS, "0") if digits else ""
    for i, digit in enumerate(digits):
        page.insert_text((NUMBER_X + i * NUMBER_PITCH, NUMBER_BASELINE), digit,
                         fontname=fonts[SERIF_BOLD], fontsize=NUMBER_SIZE,
                         color=BACK["firm_1"].colour)
