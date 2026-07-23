"""Build templates/mvd_prilozhenie_7/mapping.v1.json from auto-detected grids.

Detects the character-grid rows with ``src.pdf.calibrate`` and assigns each
required row a field id via the ASSIGNMENTS table below (established by visual
review of the overlay — the only human step). Re-run whenever the template
image changes; the coordinates are measured, never hand-typed.

    python -m scripts.calibrate_mvd
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz

from src.pdf.calibrate import GridRow, detect_grid_rows

TEMPLATE = Path("templates/mvd_prilozhenie_7/template.pdf")
OUT = Path("templates/mvd_prilozhenie_7/mapping.v1.json")

# (page, detected-row-index) -> (field_id, transform, formatter)
# Row indices are the pitch>10 rows in top-to-bottom order (see overlay images).
ASSIGNMENTS: dict[tuple[int, int], tuple[str, str | None, str | None]] = {
    (2, 3): ("company.address_full", "uppercase", None),
    (2, 7): ("employee.passport.surname", "uppercase", None),
    (2, 8): ("employee.passport.name", "uppercase", None),
    (2, 9): ("employee.passport.patronymic", "uppercase", None),
    (2, 10): ("employee.passport.nationality", "uppercase", None),
    (2, 11): ("employee.passport.birth_date.year", None, "date_yyyy"),
    (2, 13): ("employee.passport.number", None, None),
    (2, 14): ("employee.passport.issued_by", "uppercase", None),
    (3, 0): ("employee.patent.doc_name", "uppercase", None),
    (3, 1): ("employee.patent.number", None, None),
    (3, 8): ("employee.profession", "uppercase", None),
}


def _grid_field(row: GridRow, field_id: str, transform: str | None, formatter: str | None) -> dict:
    field: dict[str, object] = {
        "id": field_id,
        "type": "grid",
        "page": row.page,
        "x0": row.x0,
        "y": round(row.baseline(), 2),
        "pitch": row.pitch,
        "max_cells": row.max_cells,
        "font": "OfisSans",
        "size": 11.0,
        "align": "center",
        "_calibrated": True,
    }
    if transform:
        field["transform"] = transform
    if formatter:
        field["formatter"] = formatter
    return field


def main() -> None:
    doc = fitz.open(str(TEMPLATE))
    per_page: dict[int, list[GridRow]] = {}
    for pi in range(doc.page_count):
        per_page[pi + 1] = [r for r in detect_grid_rows(doc[pi], pi + 1) if r.pitch > 10]

    fields: list[dict] = []
    for (page, idx), (fid, transform, formatter) in ASSIGNMENTS.items():
        rows = per_page.get(page, [])
        if idx >= len(rows):
            print(f"WARN: page {page} has no row {idx}; skipped {fid}")
            continue
        fields.append(_grid_field(rows[idx], fid, transform, formatter))

    mapping = {
        "template": "mvd_prilozhenie_7",
        "template_version": "1",
        "mapping_version": "1",
        "page_size": [round(doc[0].rect.width, 1), round(doc[0].rect.height, 1)],
        "fields": sorted(fields, key=lambda f: (f["page"], f["y"])),
    }
    OUT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} with {len(fields)} calibrated fields")


if __name__ == "__main__":
    main()
