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

# Two font families, chosen per field via its "font" key:
#   OfisSans  → Calibri Bold  (the МВД trudovoy form)
#   OfisSerif → Times New Roman (the registration form)
# On Windows the real system fonts are used; elsewhere metric-compatible open
# clones (Carlito, Liberation Serif) that look identical.
_DEFAULT_FAMILY = "OfisSans"
_FONT_FAMILIES: dict[str, dict[str, object]] = {
    "OfisSans": {"nt": ("calibrib.ttf", "calibri.ttf"), "bundled": "OfisSans-Bold.ttf"},
    "OfisSerif": {"nt": ("times.ttf", "timesbd.ttf"), "bundled": "OfisSerif-Regular.ttf"},
}


def _fontname(family: str) -> str:
    """The internal PDF font name PyMuPDF registers this family under."""
    return "ofis_serif" if family == "OfisSerif" else "ofis_sans"


def _font_file(family: str) -> "Path":
    spec = _FONT_FAMILIES.get(family, _FONT_FAMILIES[_DEFAULT_FAMILY])
    if _os.name == "nt":
        for name in spec["nt"]:  # type: ignore[union-attr]
            candidate = Path(_os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
            if candidate.exists():
                return candidate
    return paths.resources_dir() / "fonts" / str(spec["bundled"])


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

    fields = mapping.calibrated_fields() if only_calibrated else mapping.fields

    # Load only the font families this mapping actually uses, register each on
    # every page under its own name, and keep a fitz.Font for width measuring.
    families = {f.font for f in fields} | {_DEFAULT_FAMILY}
    fonts: dict[str, fitz.Font] = {}
    for family in families:
        path = _font_file(family)
        if not path.exists():
            raise FontMissingError("Fill font missing", context={"path": str(path)})
        fonts[family] = fitz.Font(fontfile=str(path))

    doc = fitz.open(str(template_path))
    try:
        for page in doc:
            for family in families:
                page.insert_font(fontname=_fontname(family), fontfile=str(_font_file(family)))

        for field in fields:
            if not _visible(field, values):
                continue
            page = doc[field.page - 1]
            fam = field.font if field.font in fonts else _DEFAULT_FAMILY
            fname = _fontname(fam)
            if field.type == "mark":
                render_mark(page, field, fname)
                continue
            value = _resolve(field, values)
            if not value:
                continue
            _clear_region(page, field)
            if field.type == "grid":
                render_grid(page, field, value, fonts[fam], fname)
            elif field.type == "text":
                render_text(page, field, value, fonts[fam], fname)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path), garbage=4, deflate=True)
    finally:
        doc.close()

    log.info("Generated PDF: %s (%d fields)", output_path.name, len(fields))
    return output_path
