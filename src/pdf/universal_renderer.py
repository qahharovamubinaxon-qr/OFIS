"""УНИВЕРСАЛ — print a worker onto whichever blank the office uploaded.

The office uploads an empty form, drags its texts into place, names the
arrangement and keeps it. Printing is then the short part: for every text the
office placed, write this worker's matching value at that spot, in that size,
colour, weight, face and turn.

Two things this does that the older per-form renderers do not:

**It turns text.** Some forms print up their own edge — a медкнижка does, a
few МВД packets do — and the office needs to lay a value along it rather than
across it. Every placed text carries its own angle.

**It draws pictures.** The worker's photograph, the firm's stamp and the
signature are placed exactly like texts, but drawn as themselves. Their
`size` is their HEIGHT on the page and the width follows the picture's own
shape, so a stamp never comes out an oval.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.pdf.fonts import font_file, font_id
from src.pdf.universal_fields import (
    PICTURES,
    Field,
    UniversalData,
    values,
)

log = get_logger(__name__)

#: How thickly a one-weight face is stroked when bold was asked for.
FAUX_BOLD = 0.03
#: The turns a text may take. PyMuPDF wants one of exactly these.
TURNS = (0, 90, 180, 270)


def open_blank(template: Path | str):
    """The blank as a PDF document, whether it was uploaded as one or not.

    The office photographs some forms and scans others; both arrive here and
    both have to become pages that can be written on.
    """
    template = Path(template)
    if not template.exists():
        raise OfisError(f"Бланка топилмади: {template.name}")
    with fitz.open(str(template)) as raw:
        source = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
        return fitz.open("pdf", source.tobytes())


def page_pngs(template: Path | str, zoom: float = 1.6) -> list[bytes]:
    """Every page as a picture, for the office to arrange its texts on."""
    out: list[bytes] = []
    doc = open_blank(template)
    try:
        for page in doc:
            out.append(page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                       .tobytes("png"))
    finally:
        doc.close()
    return out


def _draw_picture(page, item: Field, png: bytes) -> None:
    """A photograph, stamp or signature at its spot, its own shape kept."""
    width, height = page.rect.width, page.rect.height
    tall = max(1.0, item.size * height)
    try:
        with fitz.open("png", png) as picture:
            shape = picture[0].rect
            wide = tall * (shape.width / shape.height) if shape.height else tall
    except Exception:                                    # noqa: BLE001
        wide = tall
    left, top = item.x * width, item.baseline * height
    page.insert_image(fitz.Rect(left, top, left + wide, top + tall),
                      stream=png, keep_proportion=True, overlay=True)


#: How far apart two lines of a machine-readable zone stand, as a multiple of
#: the type size. The standard sets the strip in OCR-B at a fixed pitch and
#: this is what that spacing comes to.
MRZ_LEADING = 1.35


def _draw_text(page, item: Field, text: str) -> None:
    """One value at its spot — as a line, as spaced letters, or as a strip."""
    width, height = page.rect.width, page.rect.height
    face, faux = font_file(item.font, item.bold)
    turn = item.rotate if item.rotate in TURNS else 0
    size = item.size * height
    common = {
        "fontsize": size, "fontfile": str(face),
        "fontname": font_id(item.font, item.bold),
        "color": item.colour, "rotate": turn,
        "render_mode": 2 if faux else 0,
        "border_width": FAUX_BOLD if faux else 0.0,
    }
    left, base = item.x * width, item.baseline * height

    for row, line in enumerate(str(text).split("\n")):
        y = base + row * size * MRZ_LEADING
        if not item.pitch:
            page.insert_text((left, y), line, **common)
            continue
        # one letter to a printed box: every character at a fixed interval,
        # which is the only way a value lands in the cells a blank prints
        step = item.pitch * width
        for index, char in enumerate(line):
            if char == " ":
                continue
            page.insert_text((left + index * step, y), char, **common)


def render(data: UniversalData, template: Path | str,
           fields: list[Field]) -> bytes:
    """The office's own blank with this worker's values written onto it."""
    texts = values(data)
    doc = open_blank(template)
    try:
        written = 0
        for item in fields:
            if item.page < 1 or item.page > doc.page_count:
                continue
            page = doc[item.page - 1]
            if item.key in PICTURES:
                png = data.picture(item.key)
                if png:
                    _draw_picture(page, item, png)
                    written += 1
                continue
            text = texts.get(item.key) or ""
            if not text:
                continue
            _draw_text(page, item, text)
            written += 1
        log.info("УНИВЕРСАЛ: %s — %d та матн, %d саҳифа",
                 Path(template).stem, written, doc.page_count)
        return doc.tobytes(garbage=4, deflate=True, deflate_images=True)
    finally:
        doc.close()


def preview_png(template: Path | str, fields: list[Field], page: int = 1,
                zoom: float = 1.2) -> bytes:
    """One page with the SAMPLE texts on it, for the office to check."""
    from src.pdf.universal_fields import sample_of

    doc = open_blank(template)
    try:
        if page < 1 or page > doc.page_count:
            page = 1
        sheet = doc[page - 1]
        for item in fields:
            if item.page != page or item.key in PICTURES:
                continue
            _draw_text(sheet, item, sample_of(item.key))
        return sheet.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
    finally:
        doc.close()


__all__ = ["FAUX_BOLD", "TURNS", "open_blank", "page_pngs", "preview_png",
           "render"]
