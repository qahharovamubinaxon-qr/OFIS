"""Where every value sits on the РАЗРЕШЕНИЕ card, and in what.

The blank is a picture — the card was scanned, so there is no text layer to
search and nothing to line up against. Every number here was measured off the
office's own pair of cards: the filled one was subtracted from the blank one
pixel by pixel, which leaves exactly the ink the operator's typist added, and
that ink was measured. So these are not guesses at a layout; they are where the
office's own printer put the words.

Two things the measurement settled that the eye would not have:

* the серия and номер on the front are **grey** (#3D3B3C), not black — every
  other value on the card is black;
* the number on the back is set one digit at a time with 34.6 pt between them,
  which is far wider than the font's own spacing. It is a grid, not a word.

Coordinates are points on the 1599 × 1092 pt page the card was scanned onto.
``x`` is the left edge of the value, ``y`` is its **baseline** — measured from
the bottom of the ink of a value with no descender, which is the baseline
itself.
"""

from __future__ import annotations

from typing import NamedTuple

#: The page the blanks are drawn on, and the card's own line rhythm.
PAGE = (1599.0, 1092.0)
LINE = 27.2                       # front: one field to the next
BACK_LINE = 26.6                  # back: the firm's three lines

#: Liberation Sans is metric-compatible with the Arial the card is set in;
#: Liberation Serif stands in for the Times the back number is set in.
SANS = "OfisArial"
SANS_BOLD = "OfisArialBold"
SERIF_BOLD = "OfisSerifBold"

BLACK = (0.016, 0.016, 0.016)
#: «Серия 77 № 1354593» is printed a shade lighter than everything else.
GREY = (0.239, 0.231, 0.235)


class Slot(NamedTuple):
    """One value: where it starts, what it is set in, and how big."""

    x: float
    baseline: float
    size: float
    font: str = SANS
    colour: tuple[float, float, float] = BLACK


# --------------------------------------------------------------- the front

#: The window the worker's photograph fills, edge to edge. 3 : 4, as the frame
#: printed on the blank is — so a portrait fitted to 3:4 lands without a gap.
PHOTO_BOX = (461.5, 510.6, 728.2, 866.4)

#: The photograph is laid on at nine parts in ten, not flat: the office wants
#: the card's own green to come through it a little, the way the printed cards
#: look. Full strength made the picture sit on top of the card rather than in
#: it.
PHOTO_OPACITY = 0.90

#: Sizes below were set by drawing the office's own card back onto its blank
#: and shrinking each value until its ink was as wide as the ink on the card,
#: to a tenth of a point.
FRONT: dict[str, Slot] = {
    # «Серия 77 № 1354593» — the two halves of one line, both grey and large
    "seria":       Slot(855.8, 571.7, 32.2, SANS, GREY),
    "number":      Slot(942.2, 571.7, 32.2, SANS, GREY),
    "surname":     Slot(882.2, 607.2, 23.5),
    "name":        Slot(833.3, 636.3, 23.5),
    "patronymic":  Slot(886.0, 663.5, 23.5),
    "birth_date":  Slot(957.1, 688.8, 23.7),
    "citizenship": Slot(927.8, 716.0, 23.5),
    # the passport (and the ИНН after it) go on their own line under the
    # «Документ удост. личность / ИНН» heading, hard against the left margin
    "document":    Slot(750.3, 768.5, 21.9),
    "activity":    Slot(968.2, 795.7, 20.6),
    "valid_from":  Slot(862.1, 898.6, 21.0),
    "valid_to":    Slot(1016.2, 898.6, 21.0),
}

# ---------------------------------------------------------------- the back

BACK: dict[str, Slot] = {
    "firm_1":    Slot(448.8, 214.1, 21.2),
    "firm_2":    Slot(448.8, 240.5, 21.2),
    "firm_inn":  Slot(448.8, 267.4, 21.3),
    "issued_on": Slot(447.8, 585.6, 26.1, SANS_BOLD),
}

#: The seven boxes of «ВВ 0035453». One digit each, left to right.
NUMBER_X = 507.8
NUMBER_PITCH = 34.6
NUMBER_BASELINE = 688.3
NUMBER_SIZE = 52.0
NUMBER_DIGITS = 7

#: «ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТРИУМФ"» is two lines on the
#: card, and two lines is all the card has room for. A name too long for them
#: at the printed size is set smaller rather than cut in half — a firm named
#: only down to its first two lines is not the firm on the contract.
FIRM_WIDTH = 400.0
#: A name that will not wrap into two lines at the printed width may use the
#: green the card leaves to the right of it before it is set smaller.
FIRM_MAX_WIDTH = 560.0
FIRM_LINES = 2
FIRM_MIN_SIZE = 12.0
