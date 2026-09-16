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

from dataclasses import replace
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


#: How close two values must sit vertically to count as the same printed
#: line, as a share of the page height.
SAME_ROW = 0.006
#: The gap left between two values that had to be pushed apart, as a share of
#: the page width - about one space at ordinary type sizes.
FLOW_GAP = 0.004

#: Measuring faces, opened once each: every value on the sheet is measured.
_FACES: dict[str, fitz.Font] = {}


def _face_of(path) -> fitz.Font:
    key = str(path)
    got = _FACES.get(key)
    if got is None:
        got = fitz.Font(fontfile=key)
        _FACES[key] = got
    return got


def text_width(page, item: Field, text: str) -> float:
    """How wide this value prints on this page, in points."""
    if not text:
        return 0.0
    if item.pitch:                 # one letter to a printed box
        return len(text) * item.pitch * page.rect.width
    face, _ = font_file(item.font, item.bold)
    return _face_of(face).text_length(text, item.size * page.rect.height)


def _lines(page, item: Field, text: str) -> list[str]:
    """The value split into the lines it prints as.

    A newline the value already carries always breaks. Beyond that, a field
    given a ``wrap`` width breaks on word boundaries, so a long FIO lands
    inside its narrow box on two or three lines instead of running off it.
    """
    rows = str(text).split("\n")
    if not item.wrap:
        return rows
    limit = item.wrap * page.rect.width
    out: list[str] = []
    for row in rows:
        words = row.split()
        if not words:
            out.append("")
            continue
        line = words[0]
        for word in words[1:]:
            trial = f"{line} {word}"
            if text_width(page, item, trial) <= limit:
                line = trial
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def flowed(doc, items: list[tuple[int, Field, str]]
           ) -> list[tuple[int, Field, str]]:
    """The same values, moved right where one would print over the next.

    The office puts FIO, birth date and sex side by side on one line; a long
    FIO used to run straight over its neighbours. Here every value on a line
    is measured and anything that would be covered starts where the one
    before it ends instead. A value that already fits is left exactly where
    the office put it, and a turned value (it runs up the sheet's edge, where
    nothing else stands) never flows.
    """
    out: list[tuple[int, Field, str]] = []
    by_page: dict[int, list[tuple[Field, str]]] = {}
    for page_no, item, text in items:
        if item.rotate in (90, 270):
            out.append((page_no, item, text))     # turned: left alone
            continue
        by_page.setdefault(page_no, []).append((item, text))

    for page_no, on_page in by_page.items():
        page = doc[page_no - 1]
        width = page.rect.width
        rows: list[list[tuple[Field, str]]] = []
        for pair in sorted(on_page, key=lambda p: (p[0].baseline, p[0].x)):
            for row in rows:
                if abs(row[0][0].baseline - pair[0].baseline) <= SAME_ROW:
                    row.append(pair)
                    break
            else:
                rows.append([pair])
        for row in rows:
            row.sort(key=lambda p: p[0].x)
            cursor = None
            for item, text in row:
                start = item.x * width
                if cursor is not None and start < cursor:
                    start = cursor
                    item = replace(item, x=start / width)
                widest = max((text_width(page, item, line)
                              for line in _lines(page, item, text)),
                             default=0.0)
                cursor = start + widest + FLOW_GAP * width
                out.append((page_no, item, text))
    return out


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

    for row, line in enumerate(_lines(page, item, text)):
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
        pending: list[tuple[int, Field, str]] = []
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
            pending.append((item.page, item, text))

        # Measured and pushed along, so a long value never prints over the one
        # standing beside it on the same line (see `flowed`).
        for page_no, item, text in flowed(doc, pending):
            _draw_text(doc[page_no - 1], item, text)
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
