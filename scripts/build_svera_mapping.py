"""Emit templates/svera/mapping.v1.json for the СФЕРА certificate + protocol.

Coordinates are measured from a filled sample (grid overlay), not auto-detected —
this form is free text on ruled lines, not character boxes. Page 1 = Протокол,
page 2 = Удостоверение. Run: ``python -m scripts.build_svera_mapping``.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path("templates/svera/mapping.v1.json")

SB = "OfisSerifBold"
SBI = "OfisSerifBoldItalic"
SR = "OfisSerif"


def t(id, page, x, y, *, font=SB, size=11.0, align="left", width=None,
      formatter=None, wrap_width=None, line_height=None, clear_rects=None):
    f = {"id": id, "type": "text", "page": page, "x": x, "y": y,
         "font": font, "size": size, "align": align, "_calibrated": True}
    if width is not None:
        f["width"] = width
    if formatter:
        f["formatter"] = formatter
    if wrap_width is not None:
        f["wrap_width"] = wrap_width
    if line_height is not None:
        f["line_height"] = line_height
    if clear_rects:
        f["clear_rects"] = clear_rects
    return f


FIELDS = [
    # ================= PAGE 1 — ПРОТОКОЛ =================
    # [6] ПО number, appended after the printed "ПРОТОКОЛ № ПО"
    t("svera.po_protocol", 1, 347, 145, font=SB, size=12),
    # [3] short date after printed "от" (title, line 3)
    t("svera.date_short", 1, 300, 163, font=SB, size=11),
    # [3] long date, top-right (Ижевск line)
    t("svera.date_long_top", 1, 448, 208, font=SB, size=12),
    # [3] long date + re-typeset "№ 4 комиссия…" (printed tail whited out)
    t("svera.date_long_prikaz", 1, 318, 223, font=SB, size=12),
    # [7] проверка sentence — whiteout the printed two lines (label above ends at
    # y≈315), re-typeset with wrap so «profession» flows inline
    t("svera.proverka", 1, 90, 325, font=SB, size=12, width=475, wrap_width=475,
      line_height=13.5,
      clear_rects=[[80, 314, 585, 329], [80, 329, 585, 344]]),
    # [2] ФИО (nominative) — three centred lines in the ФИО column
    t("svera.fio_protocol", 1, 95, 400, font=SB, size=11, align="center", width=90,
      wrap_width=90, line_height=17.5),
    # [8] 13-digit reg number, under printed "Сдал, 2079"
    t("svera.reg13", 1, 300, 440, font=SB, size=11, align="center", width=105),
    # [7] Заключение — profession + разряд, centred & wrapped in its column
    t("svera.zaklyuchenie", 1, 408, 405, font=SB, size=11, align="center", width=135,
      wrap_width=135, line_height=15),

    # ================= PAGE 2 — УДОСТОВЕРЕНИЕ =================
    # [5] удостоверение № (after printed "УДОСТОВЕРЕНИЕ №")
    t("svera.udo_number", 2, 300, 120, font=SBI, size=13),
    # [1] student photo
    {"id": "svera.photo", "type": "image", "page": 2, "x": 120, "y": 126,
     "width": 84, "height": 88, "_calibrated": True},
    # [2] ФИО dative — left panel, 3 lines
    t("svera.fio_udo_left", 2, 298, 124, font=SBI, size=15, wrap_width=160, width=160,
      line_height=26),
    # [7] profession left, «name» centred (wraps for long names)
    t("svera.prof_udo_left", 2, 205, 192, font=SBI, size=13, align="center", width=160,
      wrap_width=160, line_height=15),
    # [3] Дата выдачи (in the blank after printed "Дата выдачи:"; the printed
    # "г." follows, so no "г." here)
    t("svera.date_udo", 2, 240, 232, font=SBI, size=11),
    # [2] ФИО dative — right panel, single centred line
    t("svera.fio_udo_right", 2, 375, 115, font=SBI, size=14, align="center", width=215),
    # [7] qualification right — "name 5 (пятого) разряда", centred & wrapped
    t("svera.qual_udo_right", 2, 378, 152, font=SB, size=13, align="center", width=210,
      wrap_width=210, line_height=16),
    # [6] ПО number (after printed "№ ПО"), regular weight on this line
    t("svera.po_udo", 2, 450, 210, font=SR, size=12),
    # [3] date after printed "от" on the ООО УЦ line (printed "г." follows)
    t("svera.date_udo_right", 2, 512, 210, font=SR, size=10),
]


def main() -> None:
    mapping = {
        "template": "svera",
        "template_version": "1",
        "mapping_version": "1",
        "page_size": [595.3, 822.1],
        "fields": FIELDS,
    }
    OUT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}: {len(FIELDS)} fields")


if __name__ == "__main__":
    main()
