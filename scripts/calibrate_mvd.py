"""Build templates/mvd_prilozhenie_7/mapping.v1.json for all fill-in fields.

Each target names its field id and an approximate (page, y, x0) location; the
script matches it to the nearest auto-detected cell run (``detect_all_runs``)
and writes that run's *measured* x0/pitch/max_cells. So coordinates are never
hand-typed — only the field↔location assignment is human, taken from the
operator's annotated pages (marks 1–15).

Grid fields fill boxes on pages 2–3. Page-5 line fields (14 reg-number, 15
FIO+citizenship) are placed as text at measured line coordinates.

    python -m scripts.calibrate_mvd
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import fitz

from src.pdf.calibrate import GridRow, detect_all_runs

TEMPLATE = Path("templates/mvd_prilozhenie_7/template.pdf")
OUT = Path("templates/mvd_prilozhenie_7/mapping.v1.json")


@dataclass(frozen=True)
class Target:
    field_id: str
    page: int
    y: float  # approx baseline area
    x0: float  # approx first-cell center
    formatter: str | None = None
    transform: str | None = None
    cells: int | None = None  # cap the run length if the detected run is longer


# Marks 1–13 (pages 2–3). Approx (y, x0) read from detect_all_runs on the blank.
GRID_TARGETS: list[Target] = [
    # ---- page 2: employee identity (marks 1–4) ----
    Target("employee.surname", 2, 355, 132.5, transform="uppercase"),
    Target("employee.name", 2, 385, 132.5, transform="uppercase"),
    Target("employee.patronymic", 2, 414, 132.5, transform="uppercase"),
    Target("employee.citizenship", 2, 444, 148.3, transform="uppercase"),
    # ---- mark 5: birth date число/месяц/год ----
    Target("employee.birth.d", 2, 546, 156.2, formatter="dd"),
    Target("employee.birth.m", 2, 546, 215.1, formatter="mm"),
    Target("employee.birth.y", 2, 546, 273.9, formatter="yyyy"),
    # ---- mark 6: passport series + number ----
    Target("employee.passport.series", 2, 630, 82.4),
    Target("employee.passport.number", 2, 630, 220.0),
    # ---- mark 7: passport issue date число/месяц/год ----
    Target("employee.passport.issue.d", 2, 630, 406.4, formatter="dd", cells=2),
    Target("employee.passport.issue.m", 2, 630, 468.3, formatter="mm"),
    Target("employee.passport.issue.y", 2, 630, 509.7, formatter="yyyy"),
    # ---- mark 8: passport issued_by (first row; long text) ----
    Target("employee.passport.issued_by", 2, 668, 132.5, transform="uppercase"),
    # ---- page 3: patent ----
    # (patent.doc_name "ПАТЕНТ" is pre-printed on the blank — do not fill.)
    # mark 9: patent series + number
    Target("patent.series", 3, 134, 86.8),
    Target("patent.number", 3, 134, 223.9),
    # mark 10: patent issue date (Дата выдачи)
    Target("patent.issue.d", 3, 134, 430.9, formatter="dd", cells=2),
    Target("patent.issue.m", 3, 134, 472.3, formatter="mm"),
    Target("patent.issue.y", 3, 134, 513.6, formatter="yyyy"),
    # mark 12: patent issued_by (first row)
    Target("patent.issued_by", 3, 171, 138.2, transform="uppercase"),
    # mark 10 again: Срок действия «с» (= issue date)
    Target("patent.from.d", 3, 228, 136.7, formatter="dd"),
    Target("patent.from.m", 3, 228, 177.8, formatter="mm"),
    Target("patent.from.y", 3, 228, 219.2, formatter="yyyy"),
    # mark 11: Срок действия «по» (= issue date + 1 year)
    Target("patent.to.d", 3, 228, 313.5, formatter="dd"),
    Target("patent.to.m", 3, 228, 354.5, formatter="mm"),
    Target("patent.to.y", 3, 228, 395.6, formatter="yyyy"),
    # ---- mark 13: form date (Дата заключения договора, 3.3) ----
    Target("doc.date.d", 3, 694, 332.9, formatter="dd"),
    Target("doc.date.m", 3, 694, 374.0, formatter="mm"),
    Target("doc.date.y", 3, 694, 415.3, formatter="yyyy"),
    # (profession handled in MANUAL_GRID — its row splits under detection.)
]

# Fields whose row auto-detection mishandles (splits/merges). Geometry taken
# from reliable sibling rows on the same page. pitch is the form's true 15.84.
# `clear` = whiteout the pre-printed default (ПОДСОБНЫЙ РАБОЧИЙ) before writing
# a custom должность; only reached when a value is present.
MANUAL_GRID: list[dict] = [
    {
        "id": "employee.profession",
        "type": "grid", "page": 3, "x0": 50.4, "y": 489.0,
        "pitch": 15.84, "max_cells": 34, "font": "OfisSans", "size": 11.0,
        "align": "center", "transform": "uppercase", "_calibrated": True,
        "clear": True, "clear_top": 472.5, "clear_bottom": 495.5,
    },
]

# Page-5 «Справка» fields sit on printed lines, not boxes → text placement.
# Coordinates from horizontal-line detection on the blank (y just above line).
MANUAL_TEXT: list[dict] = [
    {
        "id": "doc.reg_number",  # mark 14 — 3-digit, auto-incremented
        "type": "text", "page": 5, "x": 180.7, "y": 65.0, "width": 196.6,
        "align": "center", "font": "OfisSans", "size": 11.0, "_calibrated": True,
    },
    {
        "id": "employee.fio_citizenship",  # mark 15 — "ФИО, ГРАЖДАНСТВО"
        "type": "text", "page": 5, "x": 40.0, "y": 321.0, "width": 520.0,
        "align": "left", "font": "OfisSans", "size": 11.0,
        "transform": "uppercase", "overflow": "shrink", "_calibrated": True,
    },
]

FORMATTER_MAP = {"dd": "date_dd", "mm": "date_mm", "yyyy": "date_yyyy"}


def _match(runs: list[GridRow], t: Target) -> GridRow | None:
    best, best_d = None, 1e9
    for r in runs:
        d = abs(r.y_top + (r.y_bottom - r.y_top) * 0.5 - t.y) + abs(r.x0 - t.x0)
        if d < best_d:
            best, best_d = r, d
    return best if best_d < 40 else None


def _grid(row: GridRow, t: Target) -> dict:
    f: dict[str, object] = {
        "id": t.field_id,
        "type": "grid",
        "page": t.page,
        "x0": row.x0,
        "y": round(row.baseline(), 2),
        "pitch": row.pitch,
        "max_cells": min(row.max_cells, t.cells) if t.cells else row.max_cells,
        "font": "OfisSans",
        "size": 11.0,
        "align": "center",
        "_calibrated": True,
    }
    if t.transform:
        f["transform"] = t.transform
    if t.formatter:
        f["formatter"] = FORMATTER_MAP[t.formatter]
    return f


def main() -> None:
    doc = fitz.open(str(TEMPLATE))
    runs_by_page = {p: detect_all_runs(doc[p - 1], p) for p in (2, 3)}

    fields: list[dict] = []
    for t in GRID_TARGETS:
        row = _match(runs_by_page[t.page], t)
        if row is None:
            print(f"WARN: no run near {t.field_id} (p{t.page} y~{t.y} x0~{t.x0})")
            continue
        fields.append(_grid(row, t))

    fields.extend(MANUAL_GRID)
    fields.extend(MANUAL_TEXT)

    mapping = {
        "template": "mvd_prilozhenie_7",
        "template_version": "1",
        "mapping_version": "1",
        "page_size": [round(doc[0].rect.width, 1), round(doc[0].rect.height, 1)],
        "fields": sorted(fields, key=lambda f: (f["page"], f["y"], f.get("x0", f.get("x", 0)))),
    }
    OUT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}: {len(fields)}/{len(GRID_TARGETS)} grid fields calibrated")


if __name__ == "__main__":
    main()
