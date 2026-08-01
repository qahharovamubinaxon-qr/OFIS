"""КРКОД РЕГ — the QR-code registration for the office's own dormitory.

Two documents, both measured pixel-by-pixel against their own empty twins:

* the **registration** — two pages: the letter-cell front and the back that
  carries the «Уведомление зарегистрировано № …» code and the QR box;
* the **подтверждение** — one small card («ИШЧИЛАР РЕГИСТРАЦИЯ РУЙХАТИ»),
  filled with the same worker, photographed to imgbb, and it is THAT link the
  QR on the back points to.

Positions are shares of the page. Cells write one character per box at
``x + i * pitch``. The подтверждение's rows alternate: on the brown rows the
value prints WHITE, on the light rows dark maroon — measured off the sample.
"""

from __future__ import annotations

from dataclasses import dataclass

FONT = "OfisSerifBold"
TEXT_SIZE = 0.0122
CELL_SIZE = 0.0125
TEXT_OPACITY = 0.92

#: The registration blank is two pages: front and back.
REG_PAGES = 2

MAROON = (0.42, 0.16, 0.10)
WHITE = (1.0, 1.0, 1.0)
BLACK = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Slot:
    page: int
    x: float
    baseline: float
    size: float = TEXT_SIZE
    pitch: float = 0.0                 # 0 → plain text; else letter-cells
    per_row: int = 0
    colour: tuple[float, float, float] = BLACK


#: The registration — worker values, measured off the filled sample.
REG_SLOTS: dict[str, Slot] = {
    # -- front: the letter-cell notice -------------------------------------
    "f_surname":      Slot(1, 0.1795, 0.1038, CELL_SIZE, pitch=0.0266, per_row=25),
    "f_name":         Slot(1, 0.1795, 0.1275, CELL_SIZE, pitch=0.0266, per_row=25),
    "f_patronymic":   Slot(1, 0.3133, 0.1512, CELL_SIZE, pitch=0.0266, per_row=20),
    "f_citizenship":  Slot(1, 0.2069, 0.1815, CELL_SIZE, pitch=0.0266, per_row=23),
    "f_birth_day":    Slot(1, 0.2617, 0.2188, CELL_SIZE, pitch=0.0266),
    "f_birth_month":  Slot(1, 0.3680, 0.2188, CELL_SIZE, pitch=0.0266),
    "f_birth_year":   Slot(1, 0.4760, 0.2188, CELL_SIZE, pitch=0.0266),
    "f_sex_male":     Slot(1, 0.7205, 0.2185, CELL_SIZE),
    "f_sex_female":   Slot(1, 0.8130, 0.2185, CELL_SIZE),
    "f_doc_number":   Slot(1, 0.6654, 0.2655, CELL_SIZE, pitch=0.0266, per_row=10),
    "f_issue_day":    Slot(1, 0.1537, 0.3100, CELL_SIZE, pitch=0.0266),
    "f_issue_month":  Slot(1, 0.2609, 0.3100, CELL_SIZE, pitch=0.0266),
    "f_issue_year":   Slot(1, 0.3431, 0.3100, CELL_SIZE, pitch=0.0266),
    "f_until_day":    Slot(1, 0.5292, 0.3100, CELL_SIZE, pitch=0.0266),
    "f_until_month":  Slot(1, 0.6364, 0.3100, CELL_SIZE, pitch=0.0266),
    "f_until_year":   Slot(1, 0.7178, 0.3100, CELL_SIZE, pitch=0.0266),
    "f_addr_subject": Slot(1, 0.1021, 0.3688, CELL_SIZE, pitch=0.0266, per_row=30),
    "f_addr_district": Slot(1, 0.1005, 0.4078, CELL_SIZE, pitch=0.0266, per_row=30),
    "f_addr_punkt":   Slot(1, 0.1005, 0.4560, CELL_SIZE, pitch=0.0266, per_row=30),
    "f_addr_street":  Slot(1, 0.1013, 0.5085, CELL_SIZE, pitch=0.0266, per_row=30),
    "f_dom":          Slot(1, 0.1050, 0.5495),
    "f_korpus":       Slot(1, 0.3950, 0.5530),
    "f_kvartira":     Slot(1, 0.1000, 0.5960),
    "f_stay_day":     Slot(1, 0.4020, 0.9465, CELL_SIZE, pitch=0.0266),
    "f_stay_month":   Slot(1, 0.5090, 0.9465, CELL_SIZE, pitch=0.0266),
    "f_stay_year":    Slot(1, 0.5885, 0.9465, CELL_SIZE, pitch=0.0266),

    # -- back: the host, the учёт date, the code ---------------------------
    "b_host_surname": Slot(2, 0.1795, 0.1687, CELL_SIZE, pitch=0.0266, per_row=25),
    "b_host_name":    Slot(2, 0.1795, 0.1922, CELL_SIZE, pitch=0.0266, per_row=25),
    "b_host_patronymic": Slot(2, 0.3140, 0.2162, CELL_SIZE, pitch=0.0266, per_row=20),
    "b_uchet_day":    Slot(2, 0.3430, 0.2978, CELL_SIZE, pitch=0.0266),
    "b_uchet_month":  Slot(2, 0.4765, 0.2978, CELL_SIZE, pitch=0.0266),
    "b_uchet_year":   Slot(2, 0.5825, 0.2978, CELL_SIZE, pitch=0.0266),
    "b_gosuslugi_owner": Slot(2, 0.1690, 0.3958, 0.0104),
    "b_code":         Slot(2, 0.6225, 0.5618, 0.0110),
}

#: Where the QR lands on the back — the printed box under the code line.
#: (x, y, width) as shares of the page; the QR is square.
QR_BOX = (0.6180, 0.5750, 0.1600)

#: The подтверждение card (284×453 pt). Left-anchored values at x 0.305; the
#: card's brown rows take WHITE type, the light rows dark maroon.
PODT_SLOTS: dict[str, Slot] = {
    "c_fio":         Slot(1, 0.3050, 0.1800, 0.0165, colour=MAROON),
    "c_birth":       Slot(1, 0.3050, 0.2025, 0.0165, colour=WHITE),
    "c_birth_place": Slot(1, 0.3050, 0.2245, 0.0165, colour=MAROON),
    "c_sex":         Slot(1, 0.3050, 0.2500, 0.0165, colour=WHITE),
    "c_citizenship": Slot(1, 0.3050, 0.2720, 0.0165, colour=MAROON),
    "c_passport":    Slot(1, 0.3050, 0.2945, 0.0165, colour=WHITE),
    "c_uchet":       Slot(1, 0.3050, 0.3205, 0.0165, colour=MAROON),
    "c_address":     Slot(1, 0.3050, 0.3455, 0.0165, colour=WHITE),
    "c_from":        Slot(1, 0.3050, 0.3680, 0.0165, colour=MAROON),
    "c_to":          Slot(1, 0.3050, 0.3895, 0.0165, colour=WHITE),
    "c_code":        Slot(1, 0.5500, 0.4125, 0.0160, colour=MAROON),
}

#: Values must never run off the подтверждение card — shrink like РУС РЕГ.
PODT_RIGHT_EDGE = 0.975
