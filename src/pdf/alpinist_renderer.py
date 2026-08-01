"""Print the АЛПИНИСТ card: texts, photo, the worker's signature, the печать."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.alpinist_spec import (
    FONT,
    IMG_SLOTS,
    PAGE_COUNT,
    SLOTS,
    TEXT_OPACITY,
    Slot,
)
from src.pdf.engine import _font_file, _fontname


@dataclass
class AlpinistData:
    """One climber's card — everything as it gets printed."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    #: «УДОСТОВЕРЕНИЕ № …» on the face — typed by the operator
    ud_number: str = ""
    #: the blank's own number on the back — counts up by itself: 145, 146…
    blank_number: str = ""
    issue_date: date | None = None
    #: the finished pictures, ready as PNG bytes
    photo_png: bytes | None = None
    sign_png: bytes | None = None
    stamp_png: bytes | None = None
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return " ".join(parts).upper()


def plus_three_years(start: date | None) -> date | None:
    """10.05.2026 → 10.05.2029 — the card runs exactly three years."""
    if start is None:
        return None
    try:
        return start.replace(year=start.year + 3)
    except ValueError:                        # 29 February
        return start.replace(year=start.year + 3, day=28)


def _dots(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def values(data: AlpinistData) -> dict[str, str]:
    """Every text slot's finished string, the sample's own manner."""
    until = plus_three_years(data.issue_date)
    return {
        "p1_number": (data.ud_number or "").strip(),
        "p1_fio_surname": (data.surname or "").strip().upper(),
        "p1_fio_name": (data.name or "").strip().upper(),
        "p1_fio_patronymic": (data.patronymic or "").strip().upper(),
        "p1_issued": f"{_dots(data.issue_date)} г." if data.issue_date else "",
        "p1_until": f"{_dots(until)} г." if until else "",
        # the owner's manner: «145 от 10.05.2026 года»
        "p2_protocol": (
            f"{data.blank_number.strip()} от {_dots(data.issue_date)} года"
            if (data.blank_number or "").strip() and data.issue_date else ""),
    }


def placed(layout: dict | None, base: dict[str, Slot]) -> dict[str, Slot]:
    """The measured slots, with anything the office dragged put on top."""
    out = dict(base)
    for key, moved in ((layout or {}).get("fields") or {}).items():
        if key in out and len(moved) == 3:
            slot = out[key]
            x, baseline, size = (float(v) for v in moved)
            out[key] = Slot(slot.page, x, baseline, size)
    return out


def _image_rect(slot: Slot, page: fitz.Page, png: bytes) -> fitz.Rect:
    """x = left, baseline = bottom, size = height; width keeps the
    picture's own proportions — images place exactly like huge glyphs."""
    pix = fitz.Pixmap(png)
    aspect = pix.width / pix.height if pix.height else 1.0
    height = slot.size * page.rect.height
    x0 = slot.x * page.rect.width
    y1 = slot.baseline * page.rect.height
    return fitz.Rect(x0, y1 - height, x0 + height * aspect, y1)


def render(data: AlpinistData, template: Path | str) -> bytes:
    """The finished two-page card as PDF bytes."""
    blank = Path(template)
    if not blank.exists():
        raise OfisError("АЛПИНИСТ бланкаси топилмади — бўлимда юкланг.")

    with fitz.open(str(blank)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        if doc.page_count < PAGE_COUNT:
            raise OfisError(
                f"Бланкада {doc.page_count} та саҳифа бор — АЛПИНИСТ "
                f"{PAGE_COUNT} саҳифали бўлиши керак.")
        fontfile = str(_font_file(FONT))
        fontname = _fontname(FONT)
        slots = placed(data.layout, SLOTS)
        for key, text in values(data).items():
            slot = slots.get(key)
            if slot is None or not text:
                continue
            page = doc[slot.page - 1]
            page.insert_text(
                (slot.x * page.rect.width, slot.baseline * page.rect.height),
                text, fontsize=slot.size * page.rect.height,
                fontfile=fontfile, fontname=fontname,
                color=(0, 0, 0), fill_opacity=TEXT_OPACITY)

        pictures = placed(data.layout, IMG_SLOTS)
        for key, png in (("img_photo", data.photo_png),
                         ("img_sign", data.sign_png),
                         ("img_stamp", data.stamp_png)):
            slot = pictures.get(key)
            if slot is None or not png:
                continue
            page = doc[slot.page - 1]
            page.insert_image(_image_rect(slot, page, png), stream=png)
        return doc.tobytes()


def output_name(data: AlpinistData) -> str:
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "ALPINIST"
    keep = "".join(c for c in stem if c.isalnum() or c in "_-")
    return f"{keep or 'ALPINIST'}.pdf"
