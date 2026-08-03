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
#: The чек's ink — the deep blue off the sample.
BLUE = (0.13, 0.16, 0.72)
TEXT_SIZE = 0.0110
TEXT_OPACITY = 1.0

MONTHS_RU = ("января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря")

#: The ИПГУ's fixed head — the worker's ИНН follows the last zero.
IPGU_PREFIX = "121000000000"


@dataclass(frozen=True)
class Slot:
    x: float
    baseline: float
    size: float = TEXT_SIZE


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
    "propis1":         Slot(0.2530, 0.9130),
    "propis2":         Slot(0.2530, 0.9350),
}

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
    parts = words.rsplit(" ", 2)
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
        "propis1": parts[0] if parts else "",
        "propis2": " ".join(parts[1:]) if len(parts) > 2 else "",
    }


def placed(layout: dict | None, base: dict[str, Slot]) -> dict[str, Slot]:
    out = dict(base)
    for key, moved in ((layout or {}).get("fields") or {}).items():
        if key in out and len(moved) == 3:
            x, baseline, size = (float(v) for v in moved)
            out[key] = Slot(x, baseline, size)
    return out


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
        for key, text in values(data).items():
            slot = slots.get(key)
            if slot is None or not text:
                continue
            page.insert_text((slot.x * width, slot.baseline * height), text,
                             fontsize=slot.size * height,
                             fontfile=fontfile, fontname=fontname,
                             color=BLUE, fill_opacity=TEXT_OPACITY)
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
