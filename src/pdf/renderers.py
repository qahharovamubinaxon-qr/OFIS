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


def _wrap_words(text: str, capacities: list[int]) -> list[str]:
    """Distribute ``text`` across rows of the given cell capacities, breaking on
    spaces so words are not split. A word longer than a row is hard-split.
    """
    words = text.split()
    lines: list[str] = []
    row = 0
    current = ""
    for word in words:
        cap = capacities[min(row, len(capacities) - 1)]
        while len(word) > cap and row < len(capacities):
            # word itself doesn't fit — flush current, hard-split the word
            if current:
                lines.append(current)
                current = ""
                row += 1
                cap = capacities[min(row, len(capacities) - 1)]
            lines.append(word[:cap])
            word = word[cap:]
            row += 1
            cap = capacities[min(row, len(capacities) - 1)] if row < len(capacities) else 0
            if row >= len(capacities):
                return lines
        candidate = f"{current} {word}".strip()
        if len(candidate) <= cap:
            current = candidate
        else:
            lines.append(current)
            row += 1
            if row >= len(capacities):
                return lines
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_row(page, x0, y, pitch, chars, font, fontname, size) -> None:
    for i, ch in enumerate(chars):
        cx = x0 + i * pitch
        w = font.text_length(ch, fontsize=size)
        page.insert_text((cx - w / 2, y), ch, fontname=fontname, fontsize=size)


def render_grid(page: fitz.Page, field: Field_, value: str, font: fitz.Font, fontname: str) -> None:
    """Draw one glyph per cell, centered. Overflow continues onto ``wrap`` rows
    (word-aware) when the mapping defines them (e.g. long «Кем выдан»)."""
    if not value or field.x0 is None or field.y is None or field.pitch is None:
        return
    wrap = (field.model_extra or {}).get("wrap") or []
    rows = [(field.x0, field.y, field.pitch, field.max_cells or len(value))]
    for w in wrap:
        rows.append((w["x0"], w["y"], w.get("pitch", field.pitch), w["max_cells"]))

    if not wrap:
        _draw_row(page, field.x0, field.y, field.pitch, value[: field.max_cells or len(value)],
                  font, fontname, field.size)
        return

    lines = _wrap_words(value, [r[3] for r in rows])
    for (x0, y, pitch, cap), line in zip(rows, lines, strict=False):
        _draw_row(page, x0, y, pitch, line[:cap], font, fontname, field.size)


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
