"""Where every value sits on the ППУ pair, as fractions of the page.

Fractions, not points, because the office has not handed over the blank yet —
they sent the *filled* pair so the type could be matched, and will upload the
empty one into the section afterwards. A fraction lands correctly on whatever
size that blank turns out to be, and on the next redesign of it too.

``x`` and ``y`` are the left edge and the BASELINE of the value, each as a share
of the page's width and height. Sizes are a share of the page height, so the
type scales with the sheet instead of shrinking on a bigger one.

These were read off the office's own filled pair by eye. They are close, and
they are meant to be corrected once: fill one card from the real blank, look at
it, and move the numbers that are out. Nothing else in the section depends on
them, so a correction here is a correction everywhere.
"""

from __future__ import annotations

from typing import NamedTuple

#: Liberation Sans is metric-compatible with the Arial the pair is set in.
SANS = "OfisArial"
SANS_BOLD = "OfisArialBold"

BLACK = (0.05, 0.05, 0.05)
#: The three values the office prints in blue — citizenship on the front, the
#: address on the back — which is how their own filled card reads.
BLUE = (0.14, 0.38, 0.68)


class Slot(NamedTuple):
    """One value: where it starts, its baseline, its size, and what in."""

    x: float
    baseline: float
    size: float
    font: str = SANS_BOLD
    colour: tuple[float, float, float] = BLACK
    #: widest the value may be before it is set smaller, as a share of the page
    width: float = 0.30


FRONT: dict[str, Slot] = {
    "fio":          Slot(0.304, 0.200, 0.0175),
    "fio_latin":    Slot(0.304, 0.259, 0.0175),
    "fio_latin_2":  Slot(0.304, 0.301, 0.0175),
    "birth_date":   Slot(0.304, 0.358, 0.0175),
    "gender":       Slot(0.309, 0.415, 0.0175),
    "citizenship":  Slot(0.309, 0.470, 0.0175),
    "citizenship_2": Slot(0.309, 0.512, 0.0175),
    "country":      Slot(0.309, 0.567, 0.0175, SANS_BOLD, BLUE),
    # «Иностранный паспорт» — the foot of the front sheet
    "passport":     Slot(0.319, 0.943, 0.0185),
}

#: The passport is printed FIVE times across the pair: once at the foot of
#: the front and four times down the head of the back, each against its own
#: «Иностранный паспорт» label. The same number every time — the back is
#: torn into four parts and filed separately, so each part must carry it.
BACK: dict[str, Slot] = {
    "passport_1":  Slot(0.238, 0.079, 0.0185),
    "passport_2":  Slot(0.238, 0.173, 0.0185),
    "passport_3":  Slot(0.239, 0.270, 0.0185),
    "passport_4":  Slot(0.243, 0.362, 0.0185),
    "date_from": Slot(0.288, 0.894, 0.0175),
    "date_to":   Slot(0.375, 0.894, 0.0175),
    "address":   Slot(0.463, 0.892, 0.0175, SANS_BOLD, BLUE, width=0.45),
}

#: A long address is broken over lines rather than shrunk into illegibility:
#: three words to a line, at most three lines. The office writes them that
#: way by hand, and «Московская обл., г. Балашиха, ул. Ленина, д. 33, корп. 2,
#: кв. 15» does not fit on one line of this sheet at a readable size.
ADDRESS_WORDS = 3
ADDRESS_LINES = 3
#: The step down to the next line, as a share of the page height.
ADDRESS_LEADING = 0.022

#: The window on the front the worker's photograph goes in, as
#: (left, top, right, bottom) shares of the page.
PHOTO_BOX = (0.702, 0.171, 0.900, 0.582)
#: Laid on at seven parts in ten, with its background cut away — the office
#: wants the card's own paper to come through it.
PHOTO_OPACITY = 0.70
