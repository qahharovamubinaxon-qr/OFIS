"""КАРТА ИНОСТРАННОГО ГРАЖДАНИНА — the card's own geometry.

Measured off the office's two blanks (1683×1058 pt each): the printed
labels' baselines give every value's line, and the blank's white boxes give
the photo frame, the QR box and the signature strip. The machine-readable
zone runs across the card's lower band in three lines.

Everything is a share of the page, so a blank rescanned at another size
changes nothing. Every slot can be dragged, resized, recoloured and turned
bold or regular by the office.
"""

from __future__ import annotations

from dataclasses import dataclass

FONT_BOLD = "OfisArialBold"
FONT_REGULAR = "OfisArial"
#: The machine zone is set in Franklin Gothic Book, the card's own face.
FONT_MRZ = "OfisFranklin"
TEXT_OPACITY = 1.0

#: The machine zone's own band, marked by the office on its card: it
#: begins under the photo frame's left corner and ends level with the
#: expiry date's last digit. The characters keep their natural spacing at
#: the sample's own size, and «<» is added until the line reaches the
#: right edge — the way the printed card fills it.
MRZ_LEFT = 0.1646
MRZ_RIGHT = 0.8707
#: The sample's glyphs measure 38 px of a 1058 pt card — cap height is
#: about seven tenths of the type size, hence this.
MRZ_SIZE = 0.0510
#: The three lines' baselines, off the sample card itself.
MRZ_BASELINES = (0.7155, 0.7684, 0.8214)

BLACK = (0.0, 0.0, 0.0)
#: The card runs five years to the day.
COVER_YEARS = 5

#: The printed boxes on the inner page, off the blank itself.
PHOTO_BOX = (0.1646, 0.2713, 0.3499, 0.6420)
QR_BOX = (0.6990, 0.2146, 0.8291, 0.4169)
SIGN_BOX = (0.3656, 0.5757, 0.5921, 0.6402)
#: How much of the box the QR/signature leaves as a margin.
QR_INSET = 0.04


@dataclass(frozen=True)
class Slot:
    """One printed value: where it goes, how big, what colour, how heavy."""

    page: int
    x: float
    baseline: float
    size: float
    bold: bool = True
    colour: tuple[float, float, float] = BLACK
    mono: bool = False


#: Value slots. Page 1 is the inner side (everything), page 2 the outer
#: side, which carries the card number alone.
SLOTS: dict[str, Slot] = {
    "fio_surname":  Slot(1, 0.3666, 0.3230, 0.0270),
    "fio_rest":     Slot(1, 0.3666, 0.3620, 0.0270),
    "birth_date":   Slot(1, 0.3666, 0.4610, 0.0250),
    "gender":       Slot(1, 0.5640, 0.4610, 0.0250),
    "citizenship":  Slot(1, 0.3666, 0.5300, 0.0250),
    "card_region":  Slot(1, 0.6610, 0.5000, 0.0250),
    "card_number":  Slot(1, 0.7372, 0.5000, 0.0270),
    "card_series":  Slot(1, 0.7372, 0.5690, 0.0270),
    "expiry":       Slot(1, 0.7372, 0.6360, 0.0270),
    "mrz1":         Slot(1, MRZ_LEFT, MRZ_BASELINES[0], MRZ_SIZE,
                         bold=False, mono=True),
    "mrz2":         Slot(1, MRZ_LEFT, MRZ_BASELINES[1], MRZ_SIZE,
                         bold=False, mono=True),
    "mrz3":         Slot(1, MRZ_LEFT, MRZ_BASELINES[2], MRZ_SIZE,
                         bold=False, mono=True),
    # the outer side: the card number, nothing else
    "back_number":  Slot(2, 0.1700, 0.7700, 0.0300, bold=False),
}

#: Running numbers the office never types — each card takes the next.
KEY_SERIAL = "karta.serial"          # the small 964390 above «Номер карты»
KEY_CARD_NO = "karta.card_number"    # 70029807586
KEY_SERIES = "karta.series"          # 0077 inside «06/30 0077»
FIRST_SERIAL = 964390
FIRST_CARD_NO = 70029807586
FIRST_SERIES = 77
#: «77» — the region the card is issued in, printed before the number.
CARD_REGION = "77"
#: «06/30» — the fixed head of the серия line.
SERIES_HEAD = "06/30"

#: The MRZ's own alphabet: everything else becomes «<».
MRZ_FILL = "<"
MRZ_LEN = 30
