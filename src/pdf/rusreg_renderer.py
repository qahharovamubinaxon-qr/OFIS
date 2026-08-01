"""Print one РУС РЕГ sheet onto the firm's blank.

Everything is placed by share of the page (:mod:`src.pdf.rusreg_spec`), so a
blank re-scanned at another size still comes out right, and anything the office
has dragged into place with the mouse overrides the measured position.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.engine import _font_file, _fontname
from src.pdf.rusreg_spec import (
    ADDRESS_WRAP,
    CENTRED,
    DOC_BIRTH,
    DOC_PASSPORT,
    FIELDS,
    FONT,
    MONTHS_RU,
    TEXT_OPACITY,
    WIDTHS,
)


@dataclass
class RusRegData:
    """One worker's sheet. Everything is already the text that gets printed."""

    reg_number: str = ""
    surname: str = ""
    name: str = ""
    patronymic: str = ""
    birth_date: date | None = None
    birth_place: str = ""
    address: str = ""
    valid_from: date | None = None
    valid_to: date | None = None
    #: True for a passport, False for a birth certificate — it decides both
    #: what the «вид» line says and which numbers are printed beside it.
    is_passport: bool = True
    doc_series: str = ""
    doc_number: str = ""
    doc_issued: date | None = None
    doc_issued_by: str = ""
    firm: str = ""
    signer: str = ""
    made_on: date | None = None
    #: Anything the office dragged with the mouse, by field name.
    layout: dict = field(default_factory=dict)

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return " ".join(parts).upper()


def ru_date(value: date | None) -> tuple[str, str, str]:
    """A date as the form writes it: day, month in the genitive, year."""
    if value is None:
        return "", "", ""
    return f"{value.day:02d}", MONTHS_RU[value.month - 1], str(value.year)


def fio_born(data: RusRegData) -> str:
    """«ФАМИЛИЯ ИМЯ ОТЧЕСТВО, 30.05.1980 ГОДА РОЖДЕНИЯ» — one line, as printed."""
    who = data.fio()
    if data.birth_date is None:
        return who
    return f"{who}, {data.birth_date:%d.%m.%Y}  ГОДА РОЖДЕНИЯ".strip()


def split_address(address: str, limit: int = ADDRESS_WRAP) -> tuple[str, str]:
    """The address over the form's two ruled lines, broken at a comma.

    Broken mid-word an address stops being an address, so the break is looked
    for at the last comma that still fits; only a single unbroken run that long
    is cut by length.
    """
    text = " ".join((address or "").split()).upper()
    if len(text) <= limit:
        return text, ""
    head = text[:limit]
    cut = head.rfind(", ")
    if cut > limit // 3:
        return text[:cut + 1].strip(), text[cut + 2:].strip()
    return head.strip(), text[limit:].strip()


def values(data: RusRegData) -> dict[str, str]:
    """Every field's finished text, keyed the way :data:`FIELDS` is."""
    line1, line2 = split_address(data.address)
    from_day, from_month, from_year = ru_date(data.valid_from)
    to_day, to_month, to_year = ru_date(data.valid_to)
    iss_day, iss_month, iss_year = ru_date(data.doc_issued)
    made_day, made_month, made_year = ru_date(data.made_on or data.valid_from)
    return {
        "reg_number": (data.reg_number or "").strip(),
        "fio_born": fio_born(data),
        "birth_place": " ".join((data.birth_place or "").split()).upper(),
        "address_1": line1,
        "address_2": line2,
        "from_day": from_day, "from_month": from_month, "from_year": from_year,
        "to_day": to_day, "to_month": to_month, "to_year": to_year,
        "doc_kind": DOC_PASSPORT if data.is_passport else DOC_BIRTH,
        "doc_series": (data.doc_series or "").strip().upper(),
        "doc_number": (data.doc_number or "").strip().upper(),
        "issued_day": iss_day, "issued_month": iss_month, "issued_year": iss_year,
        "issued_by": " ".join((data.doc_issued_by or "").split()).upper(),
        "firm": " ".join((data.firm or "").split()).upper(),
        "signer": " ".join((data.signer or "").split()).upper(),
        "made_day": made_day, "made_month": made_month, "made_year": made_year,
    }


def placed(layout: dict | None = None) -> dict[str, tuple[float, float, float]]:
    """The measured positions, with anything the office moved put on top."""
    out = dict(FIELDS)
    for key, moved in ((layout or {}).get("fields") or {}).items():
        if key in out and len(moved) == 3:
            out[key] = tuple(float(v) for v in moved)
    return out


def render(data: RusRegData, template: Path | str) -> bytes:
    """The finished sheet as PDF bytes."""
    blank = Path(template)
    if not blank.exists():
        raise OfisError("РУС РЕГ бланкаси топилмади — бўлимда бланка юкланг.")

    # a blank arrives as whichever the office happens to have — a scanned PDF
    # or a bare photograph; a picture is wrapped into a one-page PDF first
    with fitz.open(str(blank)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        if doc.page_count == 0:
            raise OfisError("Бланка бўш — ичида саҳифа йўқ.")
        page = doc[0]
        width, height = page.rect.width, page.rect.height
        fontfile = str(_font_file(FONT))
        fontname = _fontname(FONT)
        spots = placed(data.layout)

        for key, text in values(data).items():
            if not text or key not in spots:
                continue
            share_x, share_y, share_size = spots[key]
            size = share_size * height
            x = share_x * width
            squeeze = 1.0
            if key in CENTRED:
                # a day or a year written flush left on its short rule looks
                # knocked over; the form centres them
                room = WIDTHS.get(key, 0.0) * width
                x += max(0.0, (room - _text_width(text, size, fontfile)) / 2.0)
            else:
                # a ЗАГС office writes half a paragraph into «кем выдан», and
                # printed at full size it ran off the sheet's right edge. The
                # type shrinks a little first; whatever still does not fit is
                # squeezed narrower — everything stays on the blank.
                room = _RIGHT_EDGE * width - x
                text_width = _text_width(text, size, fontfile)
                if text_width > room > 0:
                    size *= max(_MIN_SHRINK, room / text_width)
                    text_width = _text_width(text, size, fontfile)
                    if text_width > room:
                        squeeze = room / text_width
            point = fitz.Point(x, share_y * height)
            morph = ((point, fitz.Matrix(squeeze, 0, 0, 1, 0, 0))
                     if squeeze < 1.0 else None)
            page.insert_text(point, text, fontsize=size,
                             fontfile=fontfile, fontname=fontname,
                             color=(0, 0, 0), fill_opacity=TEXT_OPACITY,
                             morph=morph)
        return doc.tobytes()


#: Where the sheet's ruled lines end — nothing may print past it. The rules
#: were measured at 0.9431 of the page width; a whisker of air is kept.
_RIGHT_EDGE = 0.945

#: How small the type may shrink before the text is squeezed narrower
#: instead — below ~¾ of its size it stops reading as the same hand.
_MIN_SHRINK = 0.72


def _text_width(text: str, size: float, fontfile: str | None) -> float:
    """How wide this text comes out — for centring on a rule."""
    try:
        return fitz.Font(fontfile=fontfile).text_length(text, size)
    except Exception:  # noqa: BLE001 - a missing font must not stop a sheet
        return len(text) * size * 0.5


def output_name(data: RusRegData) -> str:
    """SURNAME_NAME.pdf — the office's own filing rule."""
    parts = [p.strip().upper() for p in (data.surname, data.name) if (p or "").strip()]
    stem = "_".join(parts) or "RUSREG"
    keep = "".join(c for c in stem if c.isalnum() or c in "_-")
    return f"{keep or 'RUSREG'}.pdf"
