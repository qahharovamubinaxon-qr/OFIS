"""СТРАХОВКА МАШИНАГА — the ОСАГО policy, measured off the owner's samples.

Two insurer styles, each measured 1:1 off its own filled policy (the PDFs
carry a text layer, so every value's spot came out exact):

* **Ингосстрах** — the filled/empty pair the owner sent. The blank keeps the
  policy №, premium and coefficients pre-printed; what the office fills is
  the dates, the two ФИО, the car, the 17 VIN letter-cells, the СТС
  серия/номер, the «X» tick in section 3 and the driver rows (stars when the
  cover is unlimited — exactly as the sample).
* **РЕСО** — measured off the filled полис; its marks are «V», the VIN is
  plain text («ОТСУТСТВУЕТ» when the СТС has none) and the СТС prints as one
  joined серия+номер.

A blank uploaded into the section picks one of these as its starting map;
every slot can then be dragged and resized against that very blank.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Values print in the sans face — bold where the samples are bold.
FONT_BOLD = "OfisSans"
FONT_REGULAR = "OfisSansRegular"
TEXT_OPACITY = 0.96

MAX_DRIVERS = 4

#: What the «птичка» looks like, per insurer style — 1:1 with the samples.
MARKS = {"ingosstrah": "X", "reso": "V"}

BASE_TITLES = {"ingosstrah": "Ингосстрах услуби", "reso": "РЕСО услуби"}

#: The star row Ингосстрах prints when the policy covers anyone.
STARS_FIO = "*" * 44
STARS_VU = "****"
STARS_KBM = "**"

MONTHS_RU = ("января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря")


@dataclass(frozen=True)
class Slot:
    x: float
    baseline: float
    size: float
    bold: bool = True
    #: 0 → plain text; positive → letter-cells with this pitch (page width)
    pitch: float = 0.0
    per_row: int = 0
    #: paint the blank white from x to here before writing — the Ингосстрах
    #: blank pre-prints a dotted «с . .20 г.» template under the usage dates
    clear_to: float = 0.0
    #: exact cell CENTRES when the printed grid is not uniform — the
    #: Ингосстрах VIN row's first two boxes are wider than the rest, so a
    #: fixed pitch cannot hit them; each character centres on its own box
    cells: tuple[float, ...] = ()


#: The Ингосстрах VIN boxes' centres, off the blank's own vector lines.
VIN_CELLS = (0.3308, 0.3575, 0.3828, 0.4067, 0.4305, 0.4544, 0.4782,
             0.5020, 0.5259, 0.5498, 0.5737, 0.5976, 0.6215, 0.6455,
             0.6694, 0.6934, 0.7174)


def _ingo_rows() -> dict[str, Slot]:
    out: dict[str, Slot] = {}
    for i, base in enumerate((0.5892, 0.6016, 0.6140, 0.6263), start=1):
        out[f"dr{i}_num"] = Slot(0.0578, base, 0.0095, bold=False)
        out[f"dr{i}_fio"] = Slot(0.0939, base, 0.0095, bold=False)
        out[f"dr{i}_vu"] = Slot(0.7411, base, 0.0095, bold=False)
        out[f"dr{i}_kbm"] = Slot(0.9029, base, 0.0095, bold=False)
    out["dr5_num"] = Slot(0.0578, 0.6387, 0.0095, bold=False)
    return out


INGO_MAP: dict[str, Slot] = {
    "srok_from":      Slot(0.8525, 0.2340, 0.0095, bold=False),
    "srok_to":        Slot(0.8525, 0.2439, 0.0095, bold=False),
    "use_period":     Slot(0.0492, 0.2808, 0.0095, bold=False,
                           clear_to=0.3900),
    "strah_fio":      Slot(0.0427, 0.3096, 0.0083),
    "owner_fio":      Slot(0.0385, 0.3335, 0.0083),
    "brand":          Slot(0.1234, 0.3934, 0.0095),
    "vin":            Slot(0.3308, 0.3942, 0.0095, per_row=17,
                           cells=VIN_CELLS),
    "plate":          Slot(0.8188, 0.4048, 0.0095),
    "doc_series":     Slot(0.4270, 0.4426, 0.0095),
    "doc_number":     Slot(0.5170, 0.4426, 0.0095),
    "tick_unlimited": Slot(0.5169, 0.5251, 0.0095, bold=False),
    "tick_named":     Slot(0.8531, 0.5251, 0.0095, bold=False),
    **_ingo_rows(),
    "deal_q":         Slot(0.2220, 0.8895, 0.0095, bold=False),
    "issue_q":        Slot(0.1760, 0.9567, 0.0095, bold=False),
    "policy_no":      Slot(0.5980, 0.0930, 0.0120),
    "premium":        Slot(0.7700, 0.0290, 0.0100),
}


def _reso_rows() -> dict[str, Slot]:
    out: dict[str, Slot] = {}
    for i, base in enumerate((0.6404, 0.6551, 0.6698, 0.6845), start=1):
        out[f"dr{i}_fio"] = Slot(0.0681, base, 0.0118, bold=False)
        out[f"dr{i}_vu"] = Slot(0.6600, base, 0.0118, bold=False)
        out[f"dr{i}_kbm"] = Slot(0.8850, base, 0.0118, bold=False)
    return out


RESO_MAP: dict[str, Slot] = {
    "policy_no":      Slot(0.5389, 0.0985, 0.0190),
    "premium":        Slot(0.3934, 0.1800, 0.0143),
    "srok_from":      Slot(0.6866, 0.1716, 0.0143),
    "srok_to":        Slot(0.6868, 0.1913, 0.0143),
    "use_from":       Slot(0.5639, 0.2085, 0.0095),
    "use_to":         Slot(0.5639, 0.2183, 0.0095),
    "strah_fio":      Slot(0.1896, 0.2593, 0.0143),
    "owner_fio":      Slot(0.1896, 0.2957, 0.0143),
    "tick_no_trailer": Slot(0.8305, 0.3189, 0.0118),
    "brand":          Slot(0.0355, 0.4082, 0.0143),
    "vin":            Slot(0.4789, 0.4082, 0.0143),
    "plate":          Slot(0.7354, 0.4082, 0.0143),
    "doc_kind":       Slot(0.3601, 0.4500, 0.0143),
    "doc_number":     Slot(0.7676, 0.4500, 0.0143),
    "tick_personal":  Slot(0.0214, 0.5090, 0.0143),
    "tick_unlimited": Slot(0.3170, 0.5674, 0.0095),
    "tick_named":     Slot(0.6879, 0.5674, 0.0095),
    **_reso_rows(),
    "deal_date":      Slot(0.2066, 0.8686, 0.0138),
    "strah_short":    Slot(0.0389, 0.9212, 0.0118),
    "issue_date":     Slot(0.1713, 0.9444, 0.0083),
}

BASES: dict[str, dict[str, Slot]] = {"ingosstrah": INGO_MAP, "reso": RESO_MAP}
