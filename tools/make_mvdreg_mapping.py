"""Build templates/mvdreg maps out of the hostel ones.

The office replaced its first МВД РЕГИСТРАЦИЯ blank with a clean print of
the SAME file the ХОСТЕЛ section fills (pixel-identical, both pages), so
the hostel's calibrated maps apply verbatim. The one thing this section
does differently is the start date: not the госуслуги line but the МВД
stamp — «10 АВГ 2026», BLUE, inside the «Отметка о подтверждении» box.

Run once after changing the bundled blank.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "templates" / "hostel"
DST = REPO / "templates" / "mvdreg"

#: The blue the МВД date stamp prints in (kept from the office's sample).
STAMP_INK = [0.291, 0.676, 0.917]

#: Three address rows the hostel map sets a shade low — on this print they
#: land on the label under their cells. Baselines measured off the blank.
ADDR_Y = {"host.addr.locality": 226.0, "host.addr.settlement": 252.1,
          "host.addr.komnata": 316.5}


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    for name in ("mapping.v1.json", "address_mapping.v1.json"):
        raw = json.loads((SRC / name).read_text(encoding="utf-8"))
        raw["template"] = "mvdreg"
        for field in raw["fields"]:
            if field["id"] == "reg.stay_from":
                field.update({
                    "font": "OfisSans", "size": 13.5, "align": "center",
                    "formatter": "date_stamp_ru", "colour": STAMP_INK,
                })
            elif field["id"] in ADDR_Y:
                field["y"] = ADDR_Y[field["id"]]
        (DST / name).write_text(
            json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, "->", DST / name)


if __name__ == "__main__":
    main()
