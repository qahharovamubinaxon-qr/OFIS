"""КУК ЧЕК — the СФЕРА payment чек, printed in its own dot-matrix blue.

Everything the office marked in red on the sample changes per worker: the
date on top, the ИНН and ФИО of the patent's owner, the ИПГУ (its twelve
zeros carry the worker's ИНН), the payment identifier (the date's digits
ride inside it), the amount in three places and once in words. The face is
Matricha — the very font the чек is really printed in — in чек blue.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname
from src.utils.rus_words import amount_to_words

FONT = "OfisMatricha"
#: The чек's ink — #3f1ba6, the office's own indigo.
BLUE = (0.2471, 0.1059, 0.6510)
TEXT_SIZE = 0.0110
TEXT_OPACITY = 1.0
#: Matricha ships in ONE weight, so bold is drawn: the glyph is filled AND
#: stroked with a hairline of its own colour, which thickens it evenly
#: without touching its dot-matrix shape.
BOLD_STROKE = 0.035

MONTHS_RU = ("января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря")

#: The ИПГУ's fixed head — the worker's ИНН follows the last zero.
IPGU_PREFIX = "121000000000"


@dataclass(frozen=True)
class Slot:
    x: float
    baseline: float
    size: float = TEXT_SIZE
    #: the office may recolour any text and make it thin or thick
    colour: tuple[float, float, float] = BLUE
    bold: bool = True


#: First-pass spots off the office's sample — every one draggable.
SLOTS: dict[str, Slot] = {
    "top_date":        Slot(0.3000, 0.1900),
    "inn":             Slot(0.4870, 0.5370),
    "fam":             Slot(0.4920, 0.5600),
    "ism_otch":        Slot(0.2530, 0.5820),
    "ipgu":            Slot(0.2970, 0.7490),
    "uip":             Slot(0.2530, 0.7970),
    "summa_platezha":  Slot(0.4200, 0.8200),
    "summa":           Slot(0.3340, 0.8550),
    "itogo":           Slot(0.3200, 0.8900),
    # ONE line of words: it wraps to a second line only when the sum is
    # long enough not to fit — see _write_propis
    "propis":          Slot(0.2530, 0.9130),
}

#: How far the second line of the пропись sits below the first, and how
#: many words stay on the first line when it has to wrap. The office was
#: precise: «биринчи қаторга 4 сўз, қолгани иккинчи қаторга».
PROPIS_STEP = 0.0220
PROPIS_FIRST_WORDS = 4
#: The чек's own right margin — a line may not pass it.
RIGHT_EDGE = 0.9700

#: The печать — x = left, baseline = bottom, size = height (like АЛПИНИСТ).
IMG_SLOTS: dict[str, Slot] = {"img_stamp": Slot(0.5500, 0.9500, 0.1500)}
IMG_LABELS = {"img_stamp": "⬛ ПЕЧАТЬ"}


@dataclass
class KukChekData:
    fam: str = ""
    ism: str = ""
    otch: str = ""
    inn: str = ""
    when: date | None = None
    #: the moment of printing — its clock goes onto the top line
    at: datetime | None = None
    rubles: int = 0
    kopecks: int = 0
    stamp_png: bytes | None = None
    layout: dict = field(default_factory=dict)


def _digits(count: int) -> str:
    return "".join(random.choice("0123456789") for _ in range(count))


def uip_of(when: date | None) -> str:
    """The payment identifier — the paid day's digits ride inside it,
    exactly where the sample carries them (16 digits, ддммгггг, 8 digits)."""
    if when is None:
        return ""
    return f"{_digits(16)}{when:%d%m%Y}{_digits(8)}"


def _amount(rubles: int, kopecks: int) -> str:
    return f"{rubles:,}".replace(",", " ") + f".{kopecks:02d}"


def values(data: KukChekData, uip: str | None = None) -> dict[str, str]:
    when, at = data.when, data.at
    top = ""
    if when:
        clock = f"{at:%H:%M:%S}" if at else "10:54:53"
        top = (f"{when.day:02d} {MONTHS_RU[when.month - 1]} {when.year} "
               f"{clock} мск")
    amount = _amount(data.rubles, data.kopecks)
    words = amount_to_words(data.rubles, data.kopecks)
    words = words[:1].upper() + words[1:]
    inn = "".join(ch for ch in (data.inn or "") if ch.isdigit())
    return {
        "top_date": top,
        "inn": inn,
        "fam": (data.fam or "").strip().upper(),
        "ism_otch": " ".join(p for p in ((data.ism or "").strip().upper(),
                                         (data.otch or "").strip().upper())
                             if p),
        "ipgu": f"{IPGU_PREFIX}{inn}" if inn else "",
        "uip": uip if uip is not None else uip_of(when),
        "summa_platezha": amount,
        "summa": amount,
        "itogo": amount,
        "propis": words,
    }


def placed(layout: dict | None, base: dict[str, Slot]) -> dict[str, Slot]:
    """The measured slots, with the office's own moves and styles on top."""
    out = dict(base)
    for key, moved in ((layout or {}).get("fields") or {}).items():
        if key in out and len(moved) == 3:
            slot = out[key]
            x, baseline, size = (float(v) for v in moved)
            out[key] = Slot(x, baseline, size, colour=slot.colour,
                            bold=slot.bold)
    for key, style in ((layout or {}).get("styles") or {}).items():
        if key not in out:
            continue
        slot = out[key]
        colour = style.get("colour")
        out[key] = Slot(slot.x, slot.baseline, slot.size,
                        colour=(tuple(float(c) for c in colour) if colour
                                else slot.colour),
                        bold=bool(style.get("bold", slot.bold)))
    return out


def split_propis(words: str, room: float, measure, size: float) -> list[str]:
    """One line when it fits; otherwise four words, then the rest."""
    wide = (measure.text_length(words, size) if measure
            else len(words) * size * 0.5)
    if wide <= room:
        return [words]
    parts = words.split()
    return [" ".join(parts[:PROPIS_FIRST_WORDS]),
            " ".join(parts[PROPIS_FIRST_WORDS:])]


def render(data: KukChekData, template: Path | str) -> bytes:
    """The finished чек as PDF bytes — image blanks welcome."""
    blank = Path(template)
    if not blank.exists():
        raise OfisError("КУК ЧЕК бланкаси топилмади — бўлимда юкланг.")
    with fitz.open(str(blank)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        page = doc[0]
        width, height = page.rect.width, page.rect.height
        fontfile = str(_font_file(FONT))
        fontname = _fontname(FONT)
        slots = placed(data.layout, SLOTS)
        try:
            measure = fitz.Font(fontfile=fontfile)
        except Exception:                         # noqa: BLE001
            measure = None
        for key, text in values(data).items():
            slot = slots.get(key)
            if slot is None or not text:
                continue
            size = slot.size * height
            lines = [text]
            if key == "propis":
                room = (RIGHT_EDGE - slot.x) * width
                lines = split_propis(text, room, measure, size)
            for index, line in enumerate(lines):
                baseline = (slot.baseline + index * PROPIS_STEP) * height
                page.insert_text((slot.x * width, baseline), line,
                                 fontsize=size, fontfile=fontfile,
                                 fontname=fontname, color=slot.colour,
                                 fill_opacity=TEXT_OPACITY,
                                 render_mode=2 if slot.bold else 0,
                                 stroke_opacity=TEXT_OPACITY,
                                 border_width=BOLD_STROKE if slot.bold else 0)
        if data.stamp_png:
            slot = placed(data.layout, IMG_SLOTS)["img_stamp"]
            pix = fitz.Pixmap(data.stamp_png)
            aspect = pix.width / pix.height if pix.height else 1.0
            tall = slot.size * height
            x0 = slot.x * width
            y1 = slot.baseline * height
            page.insert_image(
                fitz.Rect(x0, y1 - tall, x0 + tall * aspect, y1),
                stream=data.stamp_png)
        return doc.tobytes()


def output_name(data: KukChekData) -> str:
    parts = [p.strip().upper() for p in (data.fam, data.ism)
             if (p or "").strip()]
    stem = "_".join(parts) or "KUKCHEK"
    keep = "".join(c for c in stem if c.isalnum() or c in "_-")
    return f"{keep or 'KUKCHEK'}.pdf"
