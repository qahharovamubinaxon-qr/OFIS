"""Print the 3-СПРАВКА packet onto the firm's six-page blank."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname
from src.pdf.spr3_spec import FONT, PAGE_COUNT, SLOTS, TEXT_OPACITY, Slot


@dataclass
class Spr3Data:
    """One worker's certificate — texts as they get printed."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    citizenship: str = ""
    birth_date: date | None = None
    pass_series: str = ""
    pass_number: str = ""
    valid_from: date | None = None
    address: str = ""
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return " ".join(parts).upper()


def year_minus_day(start: date | None) -> date | None:
    """10.07.2026 → 09.07.2027 — the certificate runs a year less a day."""
    if start is None:
        return None
    try:
        anniversary = start.replace(year=start.year + 1)
    except ValueError:                       # 29 February
        anniversary = start.replace(year=start.year + 1, day=28)
    return anniversary - timedelta(days=1)


def _dots(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def _passport(data: Spr3Data) -> str:
    series = "".join((data.pass_series or "").split())
    number = "".join((data.pass_number or "").split())
    return f"{series} {number}".strip()


def values(data: Spr3Data) -> dict[str, str]:
    """Each printed page repeats the same block; the address is page 5's.

    The start date is written THE SAME on every page, as the owner asked, and
    the end is never typed — it is always the year-minus-a-day arithmetic.
    """
    out: dict[str, str] = {}
    fio = data.fio()
    until = year_minus_day(data.valid_from)
    for page in (1, 3, 5, 6):
        out[f"p{page}_fio"] = fio
        out[f"p{page}_birth"] = _dots(data.birth_date)
        out[f"p{page}_passport"] = _passport(data)
        out[f"p{page}_citizenship"] = (data.citizenship or "").upper()
        out[f"p{page}_from"] = _dots(data.valid_from)
        out[f"p{page}_to"] = _dots(until)
    out["p5_address"] = " ".join((data.address or "").split()).upper()
    return out


def placed(layout: dict | None = None) -> dict[str, Slot]:
    """The default slots, with anything the office dragged put on top."""
    out = dict(SLOTS)
    for key, moved in ((layout or {}).get("fields") or {}).items():
        if key in out and len(moved) == 3:
            slot = out[key]
            x, baseline, size = (float(v) for v in moved)
            out[key] = Slot(slot.page, x, baseline, size)
    return out


def render(data: Spr3Data, template: Path | str) -> bytes:
    """The finished six-page certificate as PDF bytes."""
    blank = Path(template)
    if not blank.exists():
        raise OfisError("3-СПРАВКА бланкаси топилмади — бўлимда юкланг.")

    with fitz.open(str(blank)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        if doc.page_count < PAGE_COUNT:
            raise OfisError(
                f"Бланкада {doc.page_count} та саҳифа бор — 3-СПРАВКА "
                f"{PAGE_COUNT} саҳифали бўлиши керак.")
        fontfile = str(_font_file(FONT))
        fontname = _fontname(FONT)
        slots = placed(data.layout)
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
        return doc.tobytes()


def output_name(data: Spr3Data) -> str:
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "SPRAVKA3"
    keep = "".join(c for c in stem if c.isalnum() or c in "_-")
    return f"{keep or 'SPRAVKA3'}.pdf"
