"""Emit templates/registration/address_mapping.v1.json — where the ADDRESS data
goes on the blank «Уведомление о прибытии» when building a per-address template.

The blank (templates/registration/blank.pdf) has identical geometry to the
worker mapping's template, verified by detect_cell_runs. Grid rows are the
measured runs; the дом/корпус/строение/квартира boxes and page-2 владелец /
regional-number lines are measured from a grid overlay.

    python -m scripts.build_reg_address_mapping
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path("templates/registration/address_mapping.v1.json")

F = "OfisSerif"
SIZE = 11.0


def grid(id, page, x0, y, cells, *, size=SIZE):
    return {"id": id, "type": "grid", "page": page, "x0": x0, "y": y,
            "pitch": 16.02, "max_cells": cells, "font": F, "size": size,
            "align": "center", "transform": "uppercase", "_calibrated": True}


def text(id, page, x, y, *, size=SIZE, align="left", width=None, transform=None):
    f = {"id": id, "type": "text", "page": page, "x": x, "y": y,
         "font": F, "size": size, "align": align, "_calibrated": True}
    if width is not None:
        f["width"] = width
    if transform:
        f["transform"] = transform
    return f


FIELDS = [
    # ---- page 1: место пребывания (marks 1-8) ----
    grid("addr.oblast", 1, 65.5, 308.2, 31),      # 1 область (субъект РФ)
    grid("addr.raion", 1, 65.5, 342.7, 31),       # 2 район (гор./сельское поселение)
    grid("addr.gorod", 1, 65.0, 391.8, 31),       # 3 город (населенный пункт)
    grid("addr.ulitsa", 1, 65.0, 427.9, 31),      # 4 улица (улично-дорожная сеть)
    text("addr.dom", 1, 103, 466),        # 5 дом ("дом 55", as printed originals)
    text("addr.korpus", 1, 228, 466),     # 6 корпус
    text("addr.stroenie", 1, 421, 466),   # 7 строение
    text("addr.kvartira", 1, 103, 502),   # 8 квартира
    # ---- page 2: принимающая сторона (mark 9) ----
    grid("addr.host_surname", 2, 112.0, 139.6, 28),
    grid("addr.host_name", 2, 112.0, 159.6, 28),
    grid("addr.host_patronymic", 2, 192.1, 179.8, 23),
    # «Владелец:» in the госуслуги box — same small size as its surroundings
    text("addr.host_line", 2, 101, 328, size=9.0),
    # 10 — regional number under «Уведомления зарегистрированго», same size/bold
    {"id": "addr.regional_number", "type": "text", "page": 2, "x": 327, "y": 498,
     "width": 200, "align": "center", "font": "OfisSerifBold", "size": 12.0,
     "_calibrated": True},
]


def main() -> None:
    mapping = {
        "template": "registration_address",
        "template_version": "1",
        "mapping_version": "1",
        "page_size": [595.3, 842.4],
        "fields": FIELDS,
    }
    OUT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}: {len(FIELDS)} fields")


if __name__ == "__main__":
    main()
