"""The PDF engine: fill a template from a flat ``{field_id: value}`` dict.

Receives only data + a validated mapping — never touches OCR/AI/UI/DB
(PDF_ENGINE.md). The template is opened and drawn on a copy; the original is
never modified. Generation is deterministic for identical inputs.

Value resolution is intentionally simple and explicit: the caller flattens an
Employee/Company into ``{"employee.passport.surname": "АЗИМОВ", ...}`` (done by
``src.services.field_extractor`` in a later phase). The engine only knows field
ids → coordinates, which keeps it reusable across any template/domain.
"""

from __future__ import annotations

import os as _os
from pathlib import Path

import fitz  # PyMuPDF

from src.common.errors import FontMissingError, TemplateMissingError
from src.common.logging import get_logger
from src.config import paths
from src.pdf.formatters import apply_formatter, apply_transform
from src.pdf.mapping import FieldMapping, Field_
from src.pdf.renderers import render_grid, render_mark, render_text

log = get_logger(__name__)

# Values are drawn in Calibri Bold (the owner's choice — slightly bolder reads
# better in the small boxes). On Windows the real system Calibri Bold is used;
# elsewhere the bundled Carlito Bold (metric-compatible clone) — identical look.
_FONT_NAME = "ofis"
_BUNDLED_FONT = paths.resources_dir() / "fonts" / "OfisSans-Bold.ttf"


def _font_file() -> "Path":
    if _os.name == "nt":
        for name in ("calibrib.ttf", "Calibrib.ttf"):  # Calibri Bold
            candidate = Path(_os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
            if candidate.exists():
                return candidate
    return _BUNDLED_FONT


def _resolve(field: Field_, values: dict[str, object]) -> str:
    raw = values.get(field.id)
    if raw is None:
        return ""
    text = apply_formatter(raw, field.formatter)
    return apply_transform(text, field.transform)


def _clear_region(page: fitz.Page, field: Field_) -> None:
    """Whiteout a pre-printed default before writing a custom value (field 16).

    Covers the cell interiors while leaving the box borders intact (inset 1.5pt).
    Only runs for fields whose mapping sets ``clear: true``.
    """
    extra = field.model_extra or {}
    if not extra.get("clear"):
        return
    top = float(extra.get("clear_top", (field.y or 0) - field.size * 1.2))
    bottom = float(extra.get("clear_bottom", (field.y or 0) + field.size * 0.4))
    if field.type == "grid" and field.x0 is not None and field.pitch is not None:
        # Whiteout the whole cell band (fully covers the pre-printed default),
        # then redraw the vertical cell dividers so the empty grid is preserved.
        cells = field.max_cells or 1
        left = field.x0 - field.pitch / 2
        right = field.x0 + (cells - 0.5) * field.pitch
        page.draw_rect(fitz.Rect(left, top, right, bottom), color=None, fill=(1, 1, 1))
        for i in range(cells + 1):
            x = left + i * field.pitch
            page.draw_line((x, top), (x, bottom), color=(0, 0, 0), width=0.7)
    else:
        left = (field.x or 0)
        page.draw_rect(fitz.Rect(left, top, left + (field.width or 0), bottom), color=None, fill=(1, 1, 1))


def _visible(field: Field_, values: dict[str, object]) -> bool:
    """Evaluate a simple ``a.b == value`` visibility rule. No eval, no surprises."""
    if not field.visible_if:
        return True
    try:
        left, right = (s.strip() for s in field.visible_if.split("==", 1))
    except ValueError:
        return True
    return str(values.get(left, "")).lower() == right.strip().lower()


def fill(
    template_path: Path,
    mapping: FieldMapping,
    values: dict[str, object],
    output_path: Path,
    *,
    only_calibrated: bool = True,
) -> Path:
    """Fill ``template_path`` per ``mapping`` with ``values`` → ``output_path``."""
    if not template_path.exists():
        raise TemplateMissingError(
            "Template file not found", context={"path": str(template_path)}
        )

    font_file = _font_file()
    if not font_file.exists():
        raise FontMissingError("Fill font missing", context={"path": str(font_file)})

    fields = mapping.calibrated_fields() if only_calibrated else mapping.fields
    font = fitz.Font(fontfile=str(font_file))
    doc = fitz.open(str(template_path))
    try:
        for page in doc:
            page.insert_font(fontname=_FONT_NAME, fontfile=str(font_file))

        for field in fields:
            if not _visible(field, values):
                continue
            page = doc[field.page - 1]
            if field.type == "mark":
                render_mark(page, field, _FONT_NAME)
                continue
            value = _resolve(field, values)
            if not value:
                continue
            _clear_region(page, field)
            if field.type == "grid":
                render_grid(page, field, value, font, _FONT_NAME)
            elif field.type == "text":
                render_text(page, field, value, font, _FONT_NAME)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path), garbage=4, deflate=True)
    finally:
        doc.close()

    log.info("Generated PDF: %s (%d fields)", output_path.name, len(fields))
    return output_path
