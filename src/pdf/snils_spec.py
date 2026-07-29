"""Where every value sits on the СНИЛС sheet, and in what.

The office's sheet is a picture — a filled one, which is what they had to
hand — so the values were measured off it rather than guessed: the ink of each
value was found column by column, and every one of them starts at the same
x. The type was then fitted by width against five of their own values
(«ШАКИРОВА», «ЭРКИНАЙ», «ТОЛИПОВНА», «ЖЕНСКИЙ», the number itself) until the
drawn ink matched the printed ink to within a few points.

Because the bundled sheet is filled, each value is **covered before it is
written**: a white patch over the old ink, stopping short of the rule beneath
it, and the new value on top. On a genuinely empty blank — which the office
will upload later — the patch falls on white paper and does nothing at all, so
the same code serves both.

Coordinates are points on the 2480 × 3508 pt page the sheet was made at.
``y`` is the baseline.
"""

from __future__ import annotations

from typing import NamedTuple

PAGE = (2480.0, 3508.0)

SANS = "OfisArial"
SANS_BOLD = "OfisArialBold"

BLACK = (0.13, 0.13, 0.13)

#: Every value on this sheet starts here, and is set at this size.
VALUE_X = 790.0
VALUE_SIZE = 40.5
#: The cap height the values are drawn at — what the patch has to cover.
VALUE_CAP = 28.0
#: How far the patch reaches right. Short of the rule's end, so a value that
#: was longer than the new one cannot leave a tail showing.
COVER_RIGHT = 1660.0


class Slot(NamedTuple):
    x: float
    baseline: float
    size: float = VALUE_SIZE
    font: str = SANS_BOLD
    colour: tuple[float, float, float] = BLACK


#: The СНИЛС number sits on the end of its own label rather than in the value
#: column, which is why it has an x of its own.
SLOTS: dict[str, Slot] = {
    "snils":      Slot(1350.0, 502.0),
    "surname":    Slot(VALUE_X, 592.0),
    "name":       Slot(VALUE_X, 684.0),
    "patronymic": Slot(VALUE_X, 770.0),
    "birth_date": Slot(VALUE_X, 858.0),
    "birth_place": Slot(VALUE_X, 936.0),
    "gender":     Slot(VALUE_X, 1028.0),
    "reg_date":   Slot(VALUE_X, 1130.0),
}

#: What the office's own sheet carried. Used when the operator leaves the box
#: empty, so a sheet is never printed with no number on it at all.
DEFAULT_SNILS = "223-902-316 33"
