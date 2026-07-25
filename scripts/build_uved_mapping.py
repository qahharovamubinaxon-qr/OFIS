"""Emit templates/trud/uved_mapping.v1.json — the уведомление о заключении
трудового договора (госуслуги form). Coordinates extracted from a filled
text-layer sample: every value sits at x=102, ~15pt under its label, sans 10pt.
The profession value is pre-printed on firm blanks, so it is whited out and
re-typeset. Page 1 is 595×871.

    python -m scripts.build_uved_mapping
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path("templates/trud/uved_mapping.v1.json")

F = "OfisSansRegular"


def t(id, page, y, *, size=10.0, clear=None):
    # Every value line is whited out first, so a firm may upload a FILLED
    # уведомление as its template — the old worker's value is erased.
    f = {"id": id, "type": "text", "page": page, "x": 102, "y": y,
         "font": F, "size": size, "align": "left", "_calibrated": True,
         "clear_rects": clear or [[100, y - 9.0, 470, y + 1.5]]}
    return f


FIELDS = [
    # ---- page 1: worker identity ----
    t("uved.surname", 1, 679.8),
    t("uved.name", 1, 719.7),
    t("uved.patronymic", 1, 758.8),
    t("uved.birth_date", 1, 798.1),
    t("uved.gender", 1, 838.2),
    # Гражданство label closes page 1; its value opens page 2.
    t("uved.citizenship", 2, 31.7),
    t("uved.birth_place", 2, 71.3),
    # ---- page 2: passport ----
    t("uved.passport.series", 2, 197.2),
    t("uved.passport.number", 2, 237.3),
    t("uved.passport.issue_date", 2, 277.2),
    t("uved.passport.issued_by", 2, 317.2),
    # ---- page 2: patent ----
    t("uved.patent.series", 2, 425.1),
    t("uved.patent.number", 2, 465.2),
    t("uved.patent.region", 2, 505.1),
    t("uved.patent.blank_series", 2, 544.8),
    t("uved.patent.blank_number", 2, 584.7),
    # ---- page 2: профессия (pre-printed on firm blanks → whiteout first) ----
    t("uved.profession", 2, 664.7, clear=[[100, 655, 420, 668.5]]),
    # ---- page 2: дата заключения договора ----
    t("uved.contract_date", 2, 784.2),
]


def main() -> None:
    mapping = {
        "template": "trud_uvedomlenie",
        "template_version": "1",
        "mapping_version": "1",
        "page_size": [595.3, 871.0],
        "fields": FIELDS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}: {len(FIELDS)} fields")


if __name__ == "__main__":
    main()
