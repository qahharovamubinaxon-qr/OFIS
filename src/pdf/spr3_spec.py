"""3-СПРАВКА — the six-page medical certificate packet, measured.

The owner laid every value out himself: a guide PDF with the labels in RED and
the values in BLACK, page for page over the firm's blank. Every black text was
measured off that guide — position, and size from its own ink height — so the
program prints exactly where and how large the sample does. Pages 2 and 4
stay untouched.

The one date the operator picks (the start) is written all over the packet in
three manners: «16» июня 2026 г (quoted), 16.06.2026 (dots), and 16 июня 26
(the two-digit year triple). The end is never typed: always a year minus a
day. Positions are shares of the page, the house convention.
"""

from __future__ import annotations

from dataclasses import dataclass

FONT = "OfisSerifBold"
TEXT_OPACITY = 0.92

PAGE_COUNT = 6
PRINTED_PAGES: tuple[int, ...] = (1, 3, 5, 6)

#: The measured type sizes (of page height): the big serials, the ФИО lines,
#: the body rows, the scattered dates.
BIG = 0.0238
NAME = 0.0210
BODY = 0.0175
DATE = 0.0190


@dataclass(frozen=True)
class Slot:
    page: int
    x: float
    baseline: float
    size: float = BODY


SLOTS: dict[str, Slot] = {
    # -- 1: заключение психиатра-нарколога --------------------------------
    "p1_fio":        Slot(1, 0.0878, 0.3200, BIG),
    "p1_birth":      Slot(1, 0.2458, 0.3660),
    "p1_gender":     Slot(1, 0.1579, 0.4050),
    "p1_passport":   Slot(1, 0.0854, 0.4310),
    "p1_date_osvid": Slot(1, 0.3610, 0.4755),
    "p1_date_chim":  Slot(1, 0.5786, 0.5218),
    "p1_date_low":   Slot(1, 0.1426, 0.7920),

    # -- 3: «3- САХИФА» ----------------------------------------------------
    "p3_num1":       Slot(3, 0.4956, 0.2765, BIG),
    "p3_num2":       Slot(3, 0.7115, 0.2765, BIG),
    "p3_fio":        Slot(3, 0.3223, 0.4050, NAME),
    "p3_fio_lat":    Slot(3, 0.3215, 0.4360),
    "p3_pass_grajd": Slot(3, 0.3699, 0.4700),
    "p3_birth":      Slot(3, 0.4376, 0.5085),
    "p3_date_ser":   Slot(3, 0.3731, 0.5480),
    "p3_from_day":   Slot(3, 0.2917, 0.9400),
    "p3_from_month": Slot(3, 0.3691, 0.9400),
    "p3_from_year":  Slot(3, 0.4279, 0.9400),
    "p3_to_day":     Slot(3, 0.6221, 0.9400),
    "p3_to_month":   Slot(3, 0.7059, 0.9400),
    "p3_to_year":    Slot(3, 0.7703, 0.9400),

    # -- 5: «5- САХИФА» ----------------------------------------------------
    "p5_num1":       Slot(5, 0.5608, 0.3240, BIG),
    "p5_num2":       Slot(5, 0.6785, 0.3240, BIG),
    "p5_date_day":   Slot(5, 0.3392, 0.4270, DATE),
    "p5_date_month": Slot(5, 0.4658, 0.4270, DATE),
    "p5_date_yy":    Slot(5, 0.6366, 0.4270, DATE),
    "p5_fio":        Slot(5, 0.1297, 0.5000, NAME),
    "p5_birth_day":  Slot(5, 0.3199, 0.5262),
    "p5_birth_month": Slot(5, 0.4311, 0.5262),
    "p5_birth_year": Slot(5, 0.5085, 0.5262),
    "p5_citizenship": Slot(5, 0.4190, 0.5555),
    "p5_gender":     Slot(5, 0.5600, 0.5840),
    "p5_passport":   Slot(5, 0.4754, 0.6130),
    "p5_issuer":     Slot(5, 0.1015, 0.6405),
    "p5_rf":         Slot(5, 0.3578, 0.6975),
    "p5_oblast":     Slot(5, 0.3900, 0.7228),
    "p5_gorod":      Slot(5, 0.1539, 0.7520),
    "p5_ulitsa":     Slot(5, 0.1604, 0.7830),
    "p5_dom":        Slot(5, 0.5044, 0.7805),
    "p5_korpus":     Slot(5, 0.6479, 0.7805),
    "p5_kvartira":   Slot(5, 0.8276, 0.7805),
    "p5_citizen2":   Slot(5, 0.6140, 0.8090),
    "p5_citizen3":   Slot(5, 0.6930, 0.8375),
    "p5_range":      Slot(5, 0.3320, 0.8890),

    # -- 6: the start date, seven times ------------------------------------
    "p6_d1_day":   Slot(6, 0.5334, 0.1215, DATE),
    "p6_d1_month": Slot(6, 0.6600, 0.1215, DATE),
    "p6_d1_yy":    Slot(6, 0.8235, 0.1215, DATE),
    "p6_d2_day":   Slot(6, 0.5334, 0.2135, DATE),
    "p6_d2_month": Slot(6, 0.6600, 0.2135, DATE),
    "p6_d2_yy":    Slot(6, 0.8235, 0.2135, DATE),
    "p6_d3_day":   Slot(6, 0.5302, 0.2900, DATE),
    "p6_d3_month": Slot(6, 0.6559, 0.2900, DATE),
    "p6_d3_yy":    Slot(6, 0.8195, 0.2900, DATE),
    "p6_d4_day":   Slot(6, 0.5326, 0.3790, DATE),
    "p6_d4_month": Slot(6, 0.6591, 0.3790, DATE),
    "p6_d4_yy":    Slot(6, 0.8227, 0.3790, DATE),
    "p6_d5_day":   Slot(6, 0.5302, 0.4550, DATE),
    "p6_d5_month": Slot(6, 0.6551, 0.4550, DATE),
    "p6_d5_yy":    Slot(6, 0.8195, 0.4550, DATE),
    "p6_d6_day":   Slot(6, 0.5351, 0.5465, DATE),
    "p6_d6_month": Slot(6, 0.6616, 0.5465, DATE),
    "p6_d6_yy":    Slot(6, 0.8259, 0.5465, DATE),
    "p6_low_day":   Slot(6, 0.1225, 0.8470, DATE),
    "p6_low_month": Slot(6, 0.2490, 0.8470, DATE),
    "p6_low_yy":    Slot(6, 0.4126, 0.8470, DATE),
}

#: Russian months in the genitive, lowercase — «16 июня 2026».
MONTHS_RU: tuple[str, ...] = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
