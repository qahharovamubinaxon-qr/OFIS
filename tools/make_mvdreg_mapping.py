"""Build templates/mvdreg maps out of the hostel ones, fitted to the blank.

The МВД РЕГИСТРАЦИЯ blank is the same отрывная часть form the ХОСТЕЛ
section fills, scanned afresh by the office. Page 1 lands as it is; on
page 2 every row sits lower, the «Отметка о подтверждении» box carries a
printed sample date that must be whited out, and the start date is a BLUE
«10 АВГ 2026» stamp, not the госуслуги line. Run once after changing the
bundled blank; positions were measured off the blank's own pixels.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "templates" / "hostel"
DST = REPO / "templates" / "mvdreg"

#: page height in points — every measured fraction becomes points with this
H = 842.03
W = 595.28

#: page-2 rows: (x0 of the first cell's CENTRE, pitch, baseline) — every
#: number measured off the blank's own cell boxes, not carried from the
#: hostel's (its cells are 16.08pt apart, this blank's are 16.9, which by
#: the twelfth letter of ВЛАДИМИРОВНА is half a cell of drift).
P2_GRID = {
    "host.surname": (0.1732 * W, 16.9, 94.4),
    "host.name": (0.1732 * W, 16.9, 115.6),
    "host.patronymic": (0.3159 * W, 16.9, 136.2),
    "host.org": (0.3443 * W, 16.9, 157.3),
    "host.inn": (0.6294 * W, 16.8, 178.5),
}
ORG_WRAP = (0.0887 * W, 16.8, 178.5)
P2 = {"registered_until": 0.2375}

#: «Заявленный срок пребывания до» (page 1) — its own cells.
STAY_UNTIL = {"d": (0.4471 * W, 16.9), "m": (0.5608 * W, 16.9),
              "y": (0.6460 * W, 16.8)}
STAY_UNTIL_Y = 504.5

#: Page-1 date groups and the серия — first-cell centres measured off the
#: blank (the hostel's expiry group is a whole slot left of this one's).
PAGE1_GRID = {
    "reg.passport.series": (0.4825 * W, 16.5),
    "reg.birth.d": (0.2950 * W, 16.7),
    "reg.birth.m": (0.4240 * W, 16.7),
    "reg.birth.y": (0.5170 * W, 16.4),
    "reg.passport.issue.d": (0.1530 * W, 15.7),
    "reg.passport.issue.m": (0.2690 * W, 15.7),
    "reg.passport.issue.y": (0.3440 * W, 16.7),
    "reg.passport.expiry.d": (0.5350 * W, 16.7),
    "reg.passport.expiry.m": (0.6490 * W, 16.4),
    "reg.passport.expiry.y": (0.7185 * W, 16.5),
}

#: Пол — the two tick boxes' centres on the birth row.
GENDER = {"reg.gender.male": 0.735 * W - 3.0,
          "reg.gender.female": 0.870 * W - 3.0}

#: «Поставлен на учет до» — its cells' centres, measured off the blank.
UCHET = {"d": (0.3443 * W, 17.1), "m": (0.4586 * W, 16.9),
         "y": (0.5420 * W, 16.8)}

#: the blue stamp: its box, the sample to hide, the ink measured off the scan
STAMP_CENTRE_X = 0.6833 * W
STAMP_BASELINE = 0.3983 * H
STAMP_CLEAR = [0.605 * W, 0.372 * H, 0.762 * W, 0.408 * H]
STAMP_INK = [0.291, 0.676, 0.917]


def _shift(field: dict, baseline_pt: float) -> None:
    field["y"] = round(baseline_pt, 1)


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    for name in ("mapping.v1.json", "address_mapping.v1.json"):
        raw = json.loads((SRC / name).read_text(encoding="utf-8"))
        raw["template"] = "mvdreg"
        for field in raw["fields"]:
            key = field["id"].rsplit(".", 1)[-1]
            if field.get("page") == 1:
                # this blank's cells sit elsewhere than the hostel's in a
                # number of rows; every corrected value was measured off the
                # blank's own cell boxes
                if field["id"] in PAGE1_GRID:
                    x0, pitch = PAGE1_GRID[field["id"]]
                    field["x0"] = round(x0, 1)
                    field["pitch"] = pitch
                elif field["id"] == "reg.passport.number" and field.get("x0"):
                    field["x0"] = round(field["x0"] + 8.3, 1)
                elif field["id"] in GENDER:
                    field["x"] = round(GENDER[field["id"]], 1)
                if field["id"] == "host.addr.street":
                    _shift(field, 0.3320 * H)
                if field["id"].startswith("reg.stay_until"):
                    x0, pitch = STAY_UNTIL[key]
                    field["x0"] = round(x0, 1)
                    field["pitch"] = pitch
                    _shift(field, STAY_UNTIL_Y)
                continue
            if field["id"].startswith("reg.registered_until"):
                x0, pitch = UCHET[key]
                field["x0"] = round(x0, 1)
                field["pitch"] = round(pitch, 2)
                _shift(field, P2["registered_until"] * H)
            elif field["id"] in P2_GRID:
                x0, pitch, baseline = P2_GRID[field["id"]]
                field["x0"] = round(x0, 1)
                field["pitch"] = pitch
                _shift(field, baseline)
                for wrap in field.get("wrap") or []:
                    wrap["x0"] = round(ORG_WRAP[0], 1)
                    wrap["pitch"] = ORG_WRAP[1]
                    wrap["y"] = ORG_WRAP[2]
            if field["id"] == "reg.stay_from":
                field.update({
                    "type": "text", "x": round(STAMP_CENTRE_X - 123.1, 1),
                    "width": 246.2, "y": round(STAMP_BASELINE, 1),
                    "font": "OfisSans", "size": 13.5, "align": "center",
                    "formatter": "date_stamp_ru", "colour": STAMP_INK,
                    "clear_rects": [STAMP_CLEAR],
                })
        (DST / name).write_text(
            json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, "->", DST / name)


if __name__ == "__main__":
    main()
