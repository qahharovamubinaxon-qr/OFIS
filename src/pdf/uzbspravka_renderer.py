"""УЗБ СПРАВКАЛАР — one worker's certificate, drawn onto the office's sheet.

Four sheets go home about one worker and they say four different things,
but they are filled the same way: the office's own scan underneath, the
worker's own values on top, the firm's seal where the office put it, and —
once the link exists — the QR beside the four-digit code at the foot.

Nothing here talks to the network. The link and the code arrive already
made, so a certificate can be printed with or without them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.fonts import font_file, font_id
from src.pdf.uzbspravka_spec import (
    INK,
    PAGE_H,
    PAGE_W,
    SEAL_DEFAULT,
    SEAL_KEY,
    Slot,
    slots_of,
)

#: How thickly a one-weight face is stroked when bold was asked for.
FAUX_BOLD = 0.03
#: Where the QR starts out: BESIDE the four-digit code at the foot and never
#: on top of it. A square of this height is 0.127 of the width, so its right
#: edge lands at 0.687 — a finger's width clear of the code, which begins at
#: 0.708 — and its middle sits level with the code's own middle.
QR_KEY = "img_qr"
QR_DEFAULT = (0.5600, 0.7280, 0.0900)


@dataclass
class UzbData:
    """One worker, as the four certificates name him."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    #: the name as the passport prints it in Latin — «Документ выдан»
    latin_name: str = ""
    birth_date: date | None = None
    passport: str = ""
    pinfl: str = ""
    firm: str = ""
    #: «1547-1548» — the tail of the № that changes from worker to worker
    number_tail: str = ""
    #: the four digits printed at the foot, and asked for by the QR
    code: str = ""
    request_no: str = ""
    made_at: datetime | None = None
    seal_png: bytes | None = None
    qr_png: bytes | None = None
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        return " ".join(p for p in (self.surname, self.name, self.patronymic)
                        if (p or "").strip())


def values(data: UzbData, sheet: int) -> dict[str, str]:
    """Every named value on one sheet, finished."""
    when = data.made_at or datetime.now()
    born = data.birth_date
    made = {
        "made_at": when.strftime("%Y-%m-%d %H:%M:%S"),
        "created": when.strftime("%Y-%m-%d"),
        "issued_at": when.strftime("%Y-%m-%d %H:%M:%S"),
        "number_tail": (data.number_tail or "").strip(),
        "request_no": (data.request_no or "").strip(),
        "latin_name": (data.latin_name or "").strip().upper(),
        "pinfl_top": (data.pinfl or "").strip(),
        "pinfl": (data.pinfl or "").strip(),
        "passport": (data.passport or "").strip(),
        "birth_date": born.strftime("%d.%m.%Y") if born else "",
        "code": (data.code or "").strip(),
        "fio": data.fio().upper(),
        "surname": (data.surname or "").strip().upper(),
        "name": (data.name or "").strip().upper(),
        "patronymic": (data.patronymic or "").strip().upper(),
    }
    if sheet == 4:
        # this sheet writes the day and the hour, not the second
        made["issued_at"] = when.strftime("%d.%m.%Y %H:%M")
    return made


def placed(sheet: int, layout: dict) -> dict[str, Slot]:
    """The sheet's slots, wearing whatever the office dragged and restyled."""
    moved = ((layout or {}).get("fields") or {}).get(str(sheet)) or {}
    styles = ((layout or {}).get("styles") or {}).get(str(sheet)) or {}
    out: dict[str, Slot] = {}
    for key, slot in slots_of(sheet).items():
        x, baseline, size = slot.x, slot.baseline, slot.size
        spot = moved.get(key)
        if spot and len(spot) == 3:
            x, baseline, size = (float(v) for v in spot)
        chosen = styles.get(key) or {}
        out[key] = Slot(
            x, baseline, float(chosen.get("size") or size),
            bool(chosen.get("bold", slot.bold)),
            tuple(chosen.get("colour") or slot.colour)[:3],
            str(chosen.get("font") or slot.family),
            slot.align, slot.sample, slot.label)
    return out


def placed_images(sheet: int, layout: dict) -> dict[str, tuple[float, ...]]:
    """The seal and the QR: «left, BOTTOM, height», per sheet."""
    moved = ((layout or {}).get("images") or {}).get(str(sheet)) or {}
    out = {}
    for key, spot in ((SEAL_KEY, SEAL_DEFAULT), (QR_KEY, QR_DEFAULT)):
        got = moved.get(key)
        out[key] = (tuple(float(v) for v in got)
                    if got and len(got) == 3 else spot)
    return out


def render(data: UzbData, sheet: int, blank: Path | None = None) -> bytes:
    """One certificate, ready for the printer."""
    text = values(data, sheet)
    slots = placed(sheet, data.layout)
    pictures = placed_images(sheet, data.layout)
    doc = fitz.open()
    try:
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        _lay_blank(page, blank)
        for key, slot in slots.items():
            _write(page, slot, text.get(key, ""))
        for key, png in ((SEAL_KEY, data.seal_png), (QR_KEY, data.qr_png)):
            _lay_image(page, png, pictures[key])
        for extra in ((data.layout or {}).get("extra") or []):
            if int(extra.get("sheet", sheet)) != sheet:
                continue
            _write(page, Slot(
                float(extra.get("x", 0.1)), float(extra.get("baseline", 0.1)),
                float(extra.get("size", 0.011)),
                bool(extra.get("bold", False)),
                tuple(extra.get("colour") or INK)[:3],
                str(extra.get("font") or "Arial")),
                str(extra.get("text") or ""))
        return doc.tobytes()
    finally:
        doc.close()


def _lay_blank(page, blank: Path | None) -> None:
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
    """A picture by its left edge, its BOTTOM and its height."""
    if not png:
        return
    left, bottom, height = where
    try:
        shape = fitz.Pixmap(png)
        ratio = (shape.width / shape.height) if shape.height else 1.0
    except Exception:                              # noqa: BLE001
        ratio = 1.0
    top = (bottom - height) * PAGE_H
    page.insert_image(fitz.Rect(left * PAGE_W, top,
                                left * PAGE_W + height * PAGE_H * ratio,
                                bottom * PAGE_H),
                      stream=png, keep_proportion=True)


def _write(page, slot: Slot, text: str) -> None:
    if not text:
        return
    size = slot.size * PAGE_H
    face, faux = font_file(slot.family, slot.bold)
    span = fitz.Font(fontfile=str(face)).text_length(text, fontsize=size)
    x = slot.x * PAGE_W
    if slot.align == "right":
        x -= span
    elif slot.align == "centre":
        x -= span / 2
    page.insert_text((x, slot.baseline * PAGE_H), text, fontsize=size,
                     fontfile=str(face), fontname=font_id(slot.family,
                                                          slot.bold),
                     color=slot.colour, render_mode=2 if faux else 0,
                     border_width=FAUX_BOLD if faux else 0.0)


def output_stem(data: UzbData, sheet: int) -> str:
    """«ЭРГАШЕВ_УМИДЖОН_1» — the office asked for the sheet's number on it."""
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    if not parts:
        # a file called «3.pdf» tells the office nothing at all
        return f"SPRAVKA_{sheet}"
    stem = "_".join([*parts, str(sheet)])
    return "".join(c for c in stem if c.isalnum() or c in "_-") \
        or f"SPRAVKA_{sheet}"
