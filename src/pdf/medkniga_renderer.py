"""МЕД КНИЖКА — the four pages the office prints and takes to the commission.

What comes out is what the office makes by hand today: the worker's own
page, the training page, the examination page and the doctors' page, each
carrying the same book number and the same date. The examination itself,
the doctors' signatures and every stamp stay where they belong — with the
medical commission, on paper.

The office may print onto its own scanned blanks or onto plain white; both
come out of the same code, because a blank is simply a picture put under
the marks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.fonts import font_file, font_id
from src.pdf.medkniga_spec import (
    ALL_SLOTS,
    EXAM_KEYS,
    HASH_KEYS,
    IMG_DEFAULTS,
    MONTHS_SHORT,
    NUMBER_KEYS,
    PAGE_H,
    PAGE_W,
    PAGES,
    Slot,
)

#: How thickly a one-weight face is stroked when bold was asked for.
FAUX_BOLD = 0.03


def stamp_date(when: date | None) -> str:
    """«05 АВГ 2026» — the way the booklet's own stamps read."""
    if when is None:
        return ""
    return f"{when.day:02d} {MONTHS_SHORT[when.month - 1]} {when.year}"


def dotted_date(when: date | None) -> str:
    """«05. 08. 2026» — the way the training page reads."""
    if when is None:
        return ""
    return f"{when.day:02d}. {when.month:02d}. {when.year}"


def a_year_on(when: date | None) -> date | None:
    """The same day next year — 29 February lands on the 28th."""
    if when is None:
        return None
    try:
        return when.replace(year=when.year + 1)
    except ValueError:
        return when.replace(year=when.year + 1, day=28)


@dataclass
class MedKnigaData:
    """One worker's book: who, when, as what, and which booklet."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    birth_year: str = ""
    city: str = "Москва"
    position: str = ""
    number: str = ""
    exam_date: date | None = None
    photo_png: bytes | None = None
    signature_png: bytes | None = None
    #: page number → the office's own scanned blank for it, if it has one
    blanks: dict[int, Path] = field(default_factory=dict)
    layout: dict = field(default_factory=dict)

    def expires(self) -> date | None:
        return a_year_on(self.exam_date)

    def given_names(self) -> str:
        return " ".join(p for p in (self.name, self.patronymic) if p.strip())


def values(data: MedKnigaData) -> dict[str, str]:
    """Every named mark's finished text."""
    stamped = stamp_date(data.exam_date)
    made = {
        "surname": _title(data.surname),
        "given": _title(data.given_names()),
        "birth_year": (data.birth_year or "").strip(),
        "city": _title(data.city),
        # a trade is one thing, not several names: «Помощник повара»
        "position": _sentence(data.position),
        "position_hand": (data.position or "").strip().lower(),
        "trained_from": dotted_date(data.exam_date),
        "trained_to": dotted_date(data.expires()),
    }
    for key in EXAM_KEYS:
        made[key] = stamped
    number = (data.number or "").strip()
    for key in NUMBER_KEYS:
        made[key] = number
    for key in HASH_KEYS:
        made[key] = "№" if number else ""
    # page 5 prints the sign and the number as one line, the way it does
    made["number5"] = f"№ {number}" if number else ""
    return made


def _title(text: str) -> str:
    return " ".join(w.capitalize() for w in (text or "").split())


def _sentence(text: str) -> str:
    """«ПОМОЩНИК ПОВАРА» → «Помощник повара» — a trade, not a name."""
    words = " ".join((text or "").split()).lower()
    return words[:1].upper() + words[1:]


def placed(layout: dict) -> dict[str, Slot]:
    """The marks, wearing whatever the office dragged and restyled."""
    moved = (layout or {}).get("fields") or {}
    styles = (layout or {}).get("styles") or {}
    out: dict[str, Slot] = {}
    for key, slot in ALL_SLOTS.items():
        x, baseline, size = slot.x, slot.baseline, slot.size
        spot = moved.get(key)
        if spot and len(spot) == 3:
            x, baseline, size = (float(v) for v in spot)
        chosen = styles.get(key) or {}
        out[key] = Slot(
            slot.page, x, baseline, float(chosen.get("size") or size),
            tuple(chosen.get("colour") or slot.colour)[:3],
            str(chosen.get("font") or slot.family),
            bool(chosen.get("bold", slot.bold)),
            slot.rotate, slot.align, slot.sample, slot.label)
    return out


def placed_images(layout: dict) -> dict[str, tuple[int, float, float, float]]:
    """The photograph and the signature: «page, left, BOTTOM, height».

    Kept the way the editor drags a picture — by its left edge and its
    bottom — so the office moves both with the mouse like any other mark.
    """
    moved = (layout or {}).get("images") or {}
    out: dict[str, tuple[int, float, float, float]] = {}
    for key, spot in IMG_DEFAULTS.items():
        got = moved.get(key)
        if got and len(got) == 4:
            out[key] = (int(got[0]), float(got[1]), float(got[2]),
                        float(got[3]))
        else:
            out[key] = spot
    return out


def render(data: MedKnigaData) -> bytes:
    """The four pages, ready for the printer."""
    text = values(data)
    slots = placed(data.layout)
    pictures = placed_images(data.layout)
    doc = fitz.open()
    try:
        for number in range(1, PAGES + 1):
            page = doc.new_page(width=PAGE_W, height=PAGE_H)
            _lay_blank(page, data.blanks.get(number))
            for key, png in (("img_photo", data.photo_png),
                             ("img_sign", data.signature_png)):
                where = pictures[key]
                if png and where[0] == number:
                    _lay_image(page, png, where[1:])
            for key, slot in slots.items():
                if slot.page == number:
                    _write(page, slot, text.get(key, ""))
            for extra in (data.layout or {}).get("extra") or []:
                if int(extra.get("page", 1)) != number:
                    continue
                _write(page, Slot(
                    number, float(extra.get("x", 0.1)),
                    float(extra.get("baseline", 0.1)),
                    float(extra.get("size", 0.013)),
                    tuple(extra.get("colour") or (0.0, 0.0, 0.0))[:3],
                    str(extra.get("font") or "Arial"),
                    bool(extra.get("bold", False)),
                    int(extra.get("rotate", 0))), str(extra.get("text") or ""))
        return doc.tobytes()
    finally:
        doc.close()


def _lay_blank(page, blank: Path | None) -> None:
    """The office's own scanned page, put UNDER the marks."""
    if blank is None:
        return
    blank = Path(blank)
    if not blank.exists():
        raise OfisError(f"Бланка топилмади: {blank.name}")
    if blank.suffix.lower() == ".pdf":
        with fitz.open(str(blank)) as source:
            if source.page_count:
                page.show_pdf_page(page.rect, source, 0)
        return
    page.insert_image(page.rect, filename=str(blank))


def _lay_image(page, png: bytes | None, where) -> None:
    """One picture, by its left edge, its BOTTOM and its height.

    The width follows the picture's own shape, so a signature photographed
    wide stays wide and one photographed narrow stays narrow — the office
    sets how TALL it is and never has to think about the rest.
    """
    if not png or where is None:
        return
    left, bottom, height = where
    try:
        shape = fitz.Pixmap(png)
        ratio = (shape.width / shape.height) if shape.height else 1.0
    except Exception:                             # noqa: BLE001
        ratio = 1.0
    top = (bottom - height) * PAGE_H
    width = height * PAGE_H * ratio
    page.insert_image(fitz.Rect(left * PAGE_W, top,
                                left * PAGE_W + width, bottom * PAGE_H),
                      stream=png, keep_proportion=True)


def _write(page, slot: Slot, text: str) -> None:
    if not text:
        return
    size = slot.size * PAGE_H
    face, faux = font_file(slot.family, slot.bold)
    span = fitz.Font(fontfile=str(face)).text_length(text, fontsize=size)
    x, y = slot.x * PAGE_W, slot.baseline * PAGE_H
    if slot.align == "centre":
        if slot.rotate:
            y -= span / 2
        else:
            x -= span / 2
    page.insert_text((x, y), text, fontsize=size, fontfile=str(face),
                     fontname=font_id(slot.family, slot.bold),
                     color=slot.colour, rotate=slot.rotate,
                     render_mode=2 if faux else 0,
                     border_width=FAUX_BOLD if faux else 0.0)


def output_stem(data: MedKnigaData) -> str:
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "MEDKNIGA"
    return "".join(c for c in stem if c.isalnum() or c in "_-") or "MEDKNIGA"
