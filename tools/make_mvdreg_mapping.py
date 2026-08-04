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

#: page-2 baselines measured off the blank (fractions of the page height)
P2 = {
    "surname": 0.1145, "name": 0.1396, "patronymic": 0.1641,
    "org1": 0.1892, "org2": 0.2142, "registered_until": 0.2375,
}

#: The ИНН cells sit half a cell right of the hostel blank's.
INN_X0, INN_PITCH = 0.6294 * W, 16.8

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
            if field.get("page") == 1:
                # this blank's cells sit half a cell right of the hostel's in
                # three rows, and its street cells a row lower
                if field["id"] in ("reg.passport.series", "reg.passport.number",
                                   "reg.birth.m") and field.get("x0"):
                    field["x0"] = round(field["x0"] + 8.3, 1)
                if field["id"] == "host.addr.street":
                    _shift(field, 0.3320 * H)
                continue
            key = field["id"].rsplit(".", 1)[-1]
            if field["id"].startswith("reg.registered_until"):
                x0, pitch = UCHET[key]
                field["x0"] = round(x0, 1)
                field["pitch"] = round(pitch, 2)
                _shift(field, P2["registered_until"] * H)
            elif key in ("surname", "name", "patronymic"):
                _shift(field, P2[key] * H)
            elif field["id"] == "host.org":
                _shift(field, P2["org1"] * H)
                for wrap in field.get("wrap") or []:
                    wrap["y"] = round(P2["org2"] * H, 1)
            elif field["id"] == "host.inn":
                field["x0"] = round(INN_X0, 1)
                field["pitch"] = INN_PITCH
                _shift(field, P2["org2"] * H)
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
