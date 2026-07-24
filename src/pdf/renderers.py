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
    extra = field.model_extra or {}
    # A wrapping paragraph: break on spaces to `width`, stacking lines by
    # `line_height`. `\n` in the value forces a hard break. Used by the СФЕРА
    # certificate for long professions / multi-line ФИО.
    if extra.get("wrap_width") and field.width:
        _render_paragraph(page, field, value, font, fontname, float(extra["wrap_width"]))
        return
    size = field.size
    if field.overflow == "shrink" and field.width:
        size = _fit_size(value, field.width, size, font)
    if field.align in ("center", "right") and field.width:
        w = font.text_length(value, fontsize=size)
        x = x + (field.width - w) / 2 if field.align == "center" else x + field.width - w
    page.insert_text((x, field.y), value, fontname=fontname, fontsize=size)


def _render_paragraph(
    page: fitz.Page, field: Field_, value: str, font: fitz.Font, fontname: str, width: float
) -> None:
    extra = field.model_extra or {}
    size = field.size
    line_h = float(extra.get("line_height", size * 1.25))
    x0 = field.x if field.x is not None else field.x0
    if x0 is None or field.y is None:
        return
    lines: list[str] = []
    for para in value.split("\n"):
        words = para.split()
        cur = ""
        for w in words:
            cand = f"{cur} {w}".strip()
            if cur and font.text_length(cand, fontsize=size) > width:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        lines.append(cur)
    y = field.y
    for line in lines:
        x = x0
        if field.align in ("center", "right"):
            lw = font.text_length(line, fontsize=size)
            x = x0 + (width - lw) / 2 if field.align == "center" else x0 + width - lw
        page.insert_text((x, y), line, fontname=fontname, fontsize=size)
        y += line_h


def render_image(page: fitz.Page, field: Field_, path: str) -> None:
    """Place a photo inside the field's box (x, y, width, height)."""
    if field.x is None or field.y is None or not field.width or not field.height:
        return
    rect = fitz.Rect(field.x, field.y, field.x + field.width, field.y + field.height)
    try:
        page.insert_image(rect, filename=path, keep_proportion=True)
    except (RuntimeError, ValueError, FileNotFoundError):
        pass


def render_mark(page: fitz.Page, field: Field_, fontname: str) -> None:
    x = field.x if field.x is not None else field.x0
    if x is None or field.y is None:
        return
    page.insert_text((x, field.y), field.glyph, fontname=fontname, fontsize=field.size)
