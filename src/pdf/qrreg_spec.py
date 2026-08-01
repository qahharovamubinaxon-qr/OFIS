"""КРКОД РЕГ — the QR-code registration for the office's own dormitory.

Two documents, both measured pixel-by-pixel against their own empty twins:

* the **registration** — two pages: the letter-cell front and the back that
  carries the «Уведомление зарегистрировано № …» code and the QR box;
* the **подтверждение** — one small card («ИШЧИЛАР РЕГИСТРАЦИЯ РУЙХАТИ»),
  filled with the same worker, photographed to imgbb, and it is THAT link the
  QR on the back points to.

Positions are shares of the page. For letter-cell slots ``x`` is the CENTRE
of the first box and every character is centred in its own box at
``x + i * pitch`` — the cell grid itself was measured off the blank's printed
boxes, so the letters land in the middles, not on the borders. The
подтверждение is set in Arial Bold Italic like its sample: on the brown rows
the value prints sandy-gold, on the light rows dark maroon.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The registration is plain Times — its sample is not bold.
FONT = "OfisSerif"
#: The подтверждение card's own face — Arial Bold Italic, as the sample.
PODT_FONT = "OfisArialBoldItalic"
TEXT_SIZE = 0.0122
CELL_SIZE = 0.0125
TEXT_OPACITY = 0.92

#: The registration blank is two pages: front and back.
REG_PAGES = 2

#: Both measured off the filled подтверждение sample's glyph cores.
MAROON = (0.365, 0.125, 0.09)
GOLD = (0.86, 0.60, 0.40)
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
    font: str = ""                     # "" → the section's own FONT


#: The registration — the cell grid measured off the blank's printed boxes
#: (x = first box CENTRE; baseline sits the letters in the boxes' middles).
REG_SLOTS: dict[str, Slot] = {
    # -- front: the letter-cell notice -------------------------------------
    "f_surname":      Slot(1, 0.1875, 0.1029, CELL_SIZE, pitch=0.0272, per_row=28),
    "f_name":         Slot(1, 0.1875, 0.1264, CELL_SIZE, pitch=0.0272, per_row=28),
    "f_patronymic":   Slot(1, 0.3226, 0.1503, CELL_SIZE, pitch=0.0272, per_row=23),
    "f_citizenship":  Slot(1, 0.2150, 0.1811, CELL_SIZE, pitch=0.0269, per_row=27),
    "f_birth_day":    Slot(1, 0.2688, 0.2168, CELL_SIZE, pitch=0.0272),
    "f_birth_month":  Slot(1, 0.3765, 0.2168, CELL_SIZE, pitch=0.0272),
    "f_birth_year":   Slot(1, 0.4841, 0.2168, CELL_SIZE, pitch=0.0268),
    "f_sex_male":     Slot(1, 0.7260, 0.2168, CELL_SIZE, pitch=0.0272, per_row=1),
    "f_sex_female":   Slot(1, 0.8337, 0.2168, CELL_SIZE, pitch=0.0272, per_row=1),
    "f_doc_number":   Slot(1, 0.6725, 0.2644, CELL_SIZE, pitch=0.0269, per_row=10),
    "f_issue_day":    Slot(1, 0.1630, 0.3080, CELL_SIZE, pitch=0.0254),
    "f_issue_month":  Slot(1, 0.2688, 0.3080, CELL_SIZE, pitch=0.0272),
    "f_issue_year":   Slot(1, 0.3499, 0.3080, CELL_SIZE, pitch=0.0268),
    "f_until_day":    Slot(1, 0.5379, 0.3080, CELL_SIZE, pitch=0.0266),
    "f_until_month":  Slot(1, 0.6456, 0.3080, CELL_SIZE, pitch=0.0269),
    "f_until_year":   Slot(1, 0.7260, 0.3080, CELL_SIZE, pitch=0.0270),
    "f_addr_subject": Slot(1, 0.1101, 0.3657, CELL_SIZE, pitch=0.0266, per_row=31),
    "f_addr_district": Slot(1, 0.1101, 0.4067, CELL_SIZE, pitch=0.0266, per_row=31),
    "f_addr_punkt":   Slot(1, 0.1092, 0.4648, CELL_SIZE, pitch=0.0266, per_row=31),
    "f_addr_street":  Slot(1, 0.1092, 0.5076, CELL_SIZE, pitch=0.0266, per_row=31),
    "f_dom":          Slot(1, 0.1050, 0.5495),
    "f_korpus":       Slot(1, 0.3950, 0.5530),
    "f_kvartira":     Slot(1, 0.1000, 0.5960),
    "f_stay_day":     Slot(1, 0.4085, 0.9448, CELL_SIZE, pitch=0.0269),
    "f_stay_month":   Slot(1, 0.5162, 0.9448, CELL_SIZE, pitch=0.0266),
    "f_stay_year":    Slot(1, 0.5966, 0.9448, CELL_SIZE, pitch=0.0270),

    # -- back: the host, the учёт date, the code ---------------------------
    "b_host_surname": Slot(2, 0.1878, 0.1657, CELL_SIZE, pitch=0.0272, per_row=28),
    "b_host_name":    Slot(2, 0.1878, 0.1894, CELL_SIZE, pitch=0.0272, per_row=28),
    "b_host_patronymic": Slot(2, 0.3226, 0.2135, CELL_SIZE, pitch=0.0269, per_row=23),
    "b_uchet_day":    Slot(2, 0.3499, 0.2964, CELL_SIZE, pitch=0.0266),
    "b_uchet_month":  Slot(2, 0.4841, 0.2964, CELL_SIZE, pitch=0.0269),
    "b_uchet_year":   Slot(2, 0.5918, 0.2964, CELL_SIZE, pitch=0.0269),
    # the sample sets these two in bold, unlike the cells
    "b_gosuslugi_owner": Slot(2, 0.1690, 0.3958, 0.0104, font="OfisSerifBold"),
    "b_code":         Slot(2, 0.6225, 0.5618, 0.0110, font="OfisSerifBold"),
}

#: The printed QR frame on the back — its outer rectangle, measured off the
#: blank. The QR itself is drawn square, centred inside, inset past the
#: frame's thick rounded border so it never touches it.
QR_FRAME = (0.6410, 0.5740, 0.7632, 0.6564)
QR_INSET = 0.08

#: What the first release shipped as defaults. A layout the office saved
#: before the cell grid was re-measured repeats these numbers verbatim for
#: every field the office never dragged — those entries must NOT pin the
#: letters to the old spots, so the loader drops any exact legacy match.
LEGACY_REG: dict[str, tuple[float, float, float]] = {
    "f_surname": (0.1795, 0.1038, 0.0125),
    "f_name": (0.1795, 0.1275, 0.0125),
    "f_patronymic": (0.3133, 0.1512, 0.0125),
    "f_citizenship": (0.2069, 0.1815, 0.0125),
    "f_birth_day": (0.2617, 0.2188, 0.0125),
    "f_birth_month": (0.3680, 0.2188, 0.0125),
    "f_birth_year": (0.4760, 0.2188, 0.0125),
    "f_sex_male": (0.7205, 0.2185, 0.0125),
    "f_sex_female": (0.8130, 0.2185, 0.0125),
    "f_doc_number": (0.6654, 0.2655, 0.0125),
    "f_issue_day": (0.1537, 0.3100, 0.0125),
    "f_issue_month": (0.2609, 0.3100, 0.0125),
    "f_issue_year": (0.3431, 0.3100, 0.0125),
    "f_until_day": (0.5292, 0.3100, 0.0125),
    "f_until_month": (0.6364, 0.3100, 0.0125),
    "f_until_year": (0.7178, 0.3100, 0.0125),
    "f_addr_subject": (0.1021, 0.3688, 0.0125),
    "f_addr_district": (0.1005, 0.4078, 0.0125),
    "f_addr_punkt": (0.1005, 0.4560, 0.0125),
    "f_addr_street": (0.1013, 0.5085, 0.0125),
    "f_dom": (0.1050, 0.5495, 0.0122),
    "f_korpus": (0.3950, 0.5530, 0.0122),
    "f_kvartira": (0.1000, 0.5960, 0.0122),
    "f_stay_day": (0.4020, 0.9465, 0.0125),
    "f_stay_month": (0.5090, 0.9465, 0.0125),
    "f_stay_year": (0.5885, 0.9465, 0.0125),
    "b_host_surname": (0.1795, 0.1687, 0.0125),
    "b_host_name": (0.1795, 0.1922, 0.0125),
    "b_host_patronymic": (0.3140, 0.2162, 0.0125),
    "b_uchet_day": (0.3430, 0.2978, 0.0125),
    "b_uchet_month": (0.4765, 0.2978, 0.0125),
    "b_uchet_year": (0.5825, 0.2978, 0.0125),
    "b_gosuslugi_owner": (0.1690, 0.3958, 0.0104),
    "b_code": (0.6225, 0.5618, 0.0110),
}

#: The подтверждение card (284×453 pt). Left-anchored values at x 0.305; the
#: card's brown rows take sandy-GOLD type, the light rows dark maroon.
PODT_SLOTS: dict[str, Slot] = {
    "c_fio":         Slot(1, 0.3050, 0.1800, 0.0165, colour=MAROON),
    "c_birth":       Slot(1, 0.3050, 0.2025, 0.0165, colour=GOLD),
    "c_birth_place": Slot(1, 0.3050, 0.2245, 0.0165, colour=MAROON),
    "c_sex":         Slot(1, 0.3050, 0.2500, 0.0165, colour=GOLD),
    "c_citizenship": Slot(1, 0.3050, 0.2720, 0.0165, colour=MAROON),
    "c_passport":    Slot(1, 0.3050, 0.2945, 0.0165, colour=GOLD),
    "c_uchet":       Slot(1, 0.3050, 0.3205, 0.0165, colour=MAROON),
    "c_address":     Slot(1, 0.3050, 0.3455, 0.0165, colour=GOLD),
    "c_from":        Slot(1, 0.3050, 0.3680, 0.0165, colour=MAROON),
    "c_to":          Slot(1, 0.3050, 0.3895, 0.0165, colour=GOLD),
    "c_code":        Slot(1, 0.5500, 0.4125, 0.0160, colour=MAROON),
}

#: Values must never run off the подтверждение card — shrink like РУС РЕГ.
PODT_RIGHT_EDGE = 0.975
