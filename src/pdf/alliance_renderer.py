"""АЛЬЯНСКОТ 2400 — one worker onto the firm's own blank.

Every blank (the two-page удостоверение and the two справки) is uploaded by
the office and arranged the same way ТРУД-8 arranges its ТД/УВ: the office
places each value itself with :class:`~src.ui.widgets.field_editor.FieldEditor`
and gets back a plain ``list[Field]``. Printing is then, for each placed
field, either a written value (text keys) or a picture (``img_photo`` /
``img_sign``) drawn into the field's own rectangle — a photo cut 3×4 like the
АЛПИНИСТ card, the worker's ink signature.

Nothing here reads a document or decides anything: the values arrive finished
and the pictures arrive already cut.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.pdf.alliance_fields import CATALOGUE, IMG_KEYS, Field
from src.pdf.alpinist_renderer import _image_rect, plus_three_years
from src.pdf.alpinist_spec import Slot
from src.pdf.fonts import font_file, font_id

TEXT_OPACITY = 1.0
#: How thickly a one-weight face is stroked when bold was asked for.
FAUX_BOLD = 0.03


@dataclass
class AllianceData:
    """One worker, everything as the three blanks print it."""

    surname: str = ""
    name: str = ""
    patronymic: str = ""
    gender: str = ""
    ud_number: str = ""
    dolzhnost: str = ""
    start_date: date | None = None
    #: the finished pictures, ready as PNG bytes (photo cut 3×4, ink signature)
    photo_png: bytes | None = None
    sign_png: bytes | None = None
    layout: dict | None = None

    def fio(self) -> str:
        parts = [p.strip() for p in (self.surname, self.name, self.patronymic)
                 if (p or "").strip()]
        return " ".join(parts).strip()


def end_date(start: date | None) -> date | None:
    """07.09.2026 → 07.09.2029 — the card runs exactly three years."""
    return plus_three_years(start)


def _dots(value: date | None) -> str:
    return f"{value:%d.%m.%Y}" if value else ""


def values(data: AllianceData) -> dict[str, str]:
    """Every catalogue key's finished text for this worker."""
    fio = data.fio()
    return {
        "fio": fio,
        "fio_upper": fio.upper(),
        "surname": (data.surname or "").strip(),
        "name": (data.name or "").strip(),
        "patronymic": (data.patronymic or "").strip(),
        "gender": (data.gender or "").strip(),
        "ud_number": (data.ud_number or "").strip(),
        "dolzhnost": (data.dolzhnost or "").strip(),
        "start_date": _dots(data.start_date),
        "end_date": _dots(plus_three_years(data.start_date)),
    }


def _fields_of(layout: dict | None) -> list[Field]:
    raw = (layout or {}).get("fields") or []
    return [Field.from_dict(d) for d in raw if isinstance(d, dict)]


def render(data: AllianceData, template: Path | str,
           layout: dict | None = None) -> bytes:
    """The firm's blank with this worker's values and pictures on it."""
    template = Path(template)
    if not template.exists():
        raise OfisError("Бланка топилмади — бўлимда юкланг.")
    layout = layout if layout is not None else (data.layout or {})
    text = values(data)
    pictures = {"img_photo": data.photo_png, "img_sign": data.sign_png}

    with fitz.open(str(template)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        doc = fitz.open("pdf", source.tobytes())
    with doc:
        for item in _fields_of(layout):
            if item.page < 1 or item.page > doc.page_count:
                continue
            page = doc[item.page - 1]
            if item.key in IMG_KEYS:
                png = pictures.get(item.key)
                if not png:
                    continue
                slot = Slot(item.page, item.x, item.baseline, item.size)
                page.insert_image(_image_rect(slot, page, png), stream=png)
                continue
            written = text.get(item.key) or ""
            if not written or item.key not in CATALOGUE:
                continue
            pw, ph = page.rect.width, page.rect.height
            face, faux = font_file(item.font, item.bold)
            page.insert_text((item.x * pw, item.baseline * ph), written,
                             fontsize=item.size * ph, fontfile=str(face),
                             fontname=font_id(item.font, item.bold),
                             color=item.colour, fill_opacity=TEXT_OPACITY,
                             render_mode=2 if faux else 0,
                             border_width=FAUX_BOLD if faux else 0.0,
                             stroke_opacity=TEXT_OPACITY)
        return doc.tobytes(garbage=4, deflate=True, deflate_images=True)


def output_name(data: AllianceData) -> str:
    """«АШУРОВ_ДИЛМУРОД.pdf» — the worker's own name, path-safe."""
    parts = [p.strip().upper() for p in (data.surname, data.name)
             if (p or "").strip()]
    stem = "_".join(parts) or "ALLIANCE"
    keep = "".join(c for c in stem if c.isalnum() or c in "_-")
    return f"{keep or 'ALLIANCE'}.pdf"
