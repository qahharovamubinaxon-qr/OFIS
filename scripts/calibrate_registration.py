"""Build templates/registration/mapping.v1.json (Уведомление о прибытии).

Same approach as ``calibrate_mvd``: each target names a field id and an
approximate (page, y, x0); the script snaps it to the nearest auto-detected
cell run and writes that run's *measured* geometry. Detection uses the
contour-based :func:`detect_cell_runs` because this blank prints its boxes in
faint gray that stroke-projection/OTSU miss.

All fields use the serif family (OfisSerif = Times New Roman), per the form.

    python -m scripts.calibrate_registration
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import fitz

from src.pdf.calibrate import GridRow, detect_cell_runs

TEMPLATE = Path("templates/registration/template.pdf")
OUT = Path("templates/registration/mapping.v1.json")

SIZE = 12.0
FONT = "OfisSerif"
FORMATTER_MAP = {"dd": "date_dd", "mm": "date_mm", "yyyy": "date_yyyy"}


@dataclass(frozen=True)
class Target:
    field_id: str
    page: int
    y: float
    x0: float
    formatter: str | None = None
    transform: str | None = None
    cells: int | None = None


# Program-filled boxes. Address (page 1) and host ФИО (page 2) are pre-printed
# per registration address and are NOT listed here.
GRID_TARGETS: list[Target] = [
    # ---- page 1: worker identity (from patent) ----
    Target("reg.surname", 1, 86.8, 111.6, transform="uppercase"),
    Target("reg.name", 1, 106.7, 111.6, transform="uppercase"),
    Target("reg.patronymic", 1, 126.7, 192.1, transform="uppercase"),
    Target("reg.citizenship", 1, 152.6, 128.1, transform="uppercase"),
    # ---- birth date (from passport) ----
    Target("reg.birth.d", 1, 182.7, 160.1, formatter="dd", cells=2),
    Target("reg.birth.m", 1, 182.7, 224.2, formatter="mm", cells=2),
    Target("reg.birth.y", 1, 182.7, 288.2, formatter="yyyy", cells=4),
    # ---- passport серия / № ----
    Target("reg.passport.series", 1, 222.7, 287.9, cells=6),
    Target("reg.passport.number", 1, 222.7, 400.3, cells=10),
    # ---- passport Дата выдачи ----
    Target("reg.passport.issue.d", 1, 259.7, 97.0, formatter="dd", cells=2),
    Target("reg.passport.issue.m", 1, 259.7, 160.1, formatter="mm", cells=2),
    Target("reg.passport.issue.y", 1, 259.7, 208.2, formatter="yyyy", cells=4),
    # ---- passport Срок действия до (expiry) ----
    Target("reg.passport.expiry.d", 1, 259.7, 320.2, formatter="dd", cells=2),
    Target("reg.passport.expiry.m", 1, 259.7, 384.3, formatter="mm", cells=2),
    Target("reg.passport.expiry.y", 1, 259.7, 432.4, formatter="yyyy", cells=4),
    # ---- Заявленный срок пребывания до (registration expiry) ----
    Target("reg.stay_until.d", 1, 796.0, 243.2, formatter="dd", cells=2),
    Target("reg.stay_until.m", 1, 796.0, 307.3, formatter="mm", cells=2),
    Target("reg.stay_until.y", 1, 796.0, 355.3, formatter="yyyy", cells=4),
    # ---- page 2: Поставлен на учет до (= registration expiry) ----
    Target("reg.registered_until.d", 2, 249.7, 208.2, formatter="dd", cells=2),
    Target("reg.registered_until.m", 2, 249.7, 288.2, formatter="mm", cells=2),
    Target("reg.registered_until.y", 2, 249.7, 352.3, formatter="yyyy", cells=4),
]

# Пол — two lone checkboxes (мужской / женский). The row detects as a single
# 2-cell run at pitch≈64; take its geometry so the two cell centers are exact.
# The builder writes "V" into whichever cell applies (empty → skipped).
GENDER_ROW = Target("_gender", 1, 182.7, 432.4)


def _match(runs: list[GridRow], t: Target) -> GridRow | None:
    best, best_d = None, 1e9
    for r in runs:
        d = abs(r.baseline() - t.y) + abs(r.x0 - t.x0)
        if d < best_d:
            best, best_d = r, d
    return best if best_d < 30 else None


def _grid(row: GridRow, t: Target) -> dict:
    f: dict[str, object] = {
        "id": t.field_id,
        "type": "grid",
        "page": t.page,
        "x0": row.x0,
        "y": round(row.baseline(), 2),
        "pitch": row.pitch,
        "max_cells": min(row.max_cells, t.cells) if t.cells else row.max_cells,
        "font": FONT,
        "size": SIZE,
        "align": "center",
        "_calibrated": True,
    }
    if t.transform:
        f["transform"] = t.transform
    if t.formatter:
        f["formatter"] = FORMATTER_MAP[t.formatter]
    return f


def _gender_cells(runs: list[GridRow]) -> list[dict]:
    row = _match(runs, GENDER_ROW)
    if row is None:
        print("WARN: gender row not found")
        return []
    male_x0 = row.x0
    female_x0 = round(row.x0 + row.pitch, 2)
    common = {
        "type": "grid", "page": 1, "y": round(row.baseline(), 2),
        "pitch": row.pitch, "max_cells": 1, "font": FONT, "size": SIZE,
        "align": "center", "_calibrated": True,
    }
    return [
        {"id": "reg.gender.male", "x0": male_x0, **common},
        {"id": "reg.gender.female", "x0": female_x0, **common},
    ]


def main() -> None:
    doc = fitz.open(str(TEMPLATE))
    runs_by_page = {p: detect_cell_runs(doc[p - 1], p) for p in (1, 2)}

    fields: list[dict] = []
    for t in GRID_TARGETS:
        row = _match(runs_by_page[t.page], t)
        if row is None:
            print(f"WARN: no run near {t.field_id} (p{t.page} y~{t.y} x0~{t.x0})")
            continue
        fields.append(_grid(row, t))

    fields.extend(_gender_cells(runs_by_page[1]))

    mapping = {
        "template": "registration",
        "template_version": "1",
        "mapping_version": "1",
        "page_size": [round(doc[0].rect.width, 1), round(doc[0].rect.height, 1)],
        "fields": sorted(fields, key=lambda f: (f["page"], f["y"], f.get("x0", 0))),
    }
    OUT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}: {len(fields)} fields")


if __name__ == "__main__":
    main()
