"""Low-level drawing primitives on a PyMuPDF page. One function per field type.

These are the only place that talks to the PDF library's drawing API. They take
already-formatted strings, a :class:`~src.pdf.mapping.Field_`, an embedded
``fitz.Font`` (for accurate Cyrillic glyph widths) and the registered font name.
Coordinates are in points, origin top-left.
"""

from __future__ import annotations

import fitz  # PyMuPDF

from src.pdf.mapping import Field_


def _fit_size(text: str, max_width: float, size: float, font: fitz.Font) -> float:
    while size > 5 and font.text_length(text, fontsize=size) > max_width:
        size -= 0.5
    return size


def render_grid(page: fitz.Page, field: Field_, value: str, font: fitz.Font, fontname: str) -> None:
    """Draw one glyph of ``value`` per cell, centered on each cell's x."""
    if not value or field.x0 is None or field.y is None or field.pitch is None:
        return
    chars = value[: field.max_cells] if field.max_cells else value
    for i, ch in enumerate(chars):
        cx = field.x0 + i * field.pitch
        w = font.text_length(ch, fontsize=field.size)
        page.insert_text((cx - w / 2, field.y), ch, fontname=fontname, fontsize=field.size)


def render_text(page: fitz.Page, field: Field_, value: str, font: fitz.Font, fontname: str) -> None:
    if not value:
        return
    x = field.x if field.x is not None else field.x0
    if x is None or field.y is None:
        return
    size = field.size
    if field.overflow == "shrink" and field.width:
        size = _fit_size(value, field.width, size, font)
    if field.align in ("center", "right") and field.width:
        w = font.text_length(value, fontsize=size)
        x = x + (field.width - w) / 2 if field.align == "center" else x + field.width - w
    page.insert_text((x, field.y), value, fontname=fontname, fontsize=size)


def render_mark(page: fitz.Page, field: Field_, fontname: str) -> None:
    x = field.x if field.x is not None else field.x0
    if x is None or field.y is None:
        return
    page.insert_text((x, field.y), field.glyph, fontname=fontname, fontsize=field.size)
