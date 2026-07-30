"""Where the ПЕРЕВОД package puts things on the office's own three blanks.

The office prints notarial translations on its own pre-printed sheets: a first
sheet the copy of the original is pasted onto, a second the translation is set
on, and a third that stays empty (the notary's own certification sheet — he
fills and stamps it by hand, so the program writes nothing on it at all).

The blanks are uploaded by the office at runtime, so nothing here is in points:
every number is a share of the page, which lands correctly whatever size the
uploaded sheet turns out to be and on the next redesign of it too.

These are the sensible defaults, meant to be corrected once: print one package
from the real blanks, look at it, and move the numbers that are out. Nothing
else in the section depends on them.
"""

from __future__ import annotations

#: The three sheets, in printing order. Stored under these stems with whatever
#: suffix the office uploaded (``page1.pdf``, ``page1.jpg`` …).
BLANK_STEMS = ("page1", "page2", "page3")

#: Long side of a generated sheet when there is no blank to take a size from
#: (A4 at 72 dpi). A blank keeps its OWN proportions — see ``_blank_page``.
A4_LONG = 842.0
A4_SHORT = 595.0

#: Sheet 1 — the window the copy of the original is centred in, as
#: (left, top, right, bottom) shares of the page.
SCAN_BOX = (0.08, 0.11, 0.92, 0.90)
#: A gap between two originals stacked in that window, as a share of its height.
SCAN_GAP = 0.02

#: Sheet 2 — the block the translation is set in.
TEXT_BOX = (0.11, 0.10, 0.89, 0.93)
#: The type size the translation starts at, as a share of the page height; it
#: is stepped down until the whole translation fits the block on ONE sheet.
TEXT_SIZE = 0.0131
TEXT_SIZE_MIN = 0.0060
#: How much of the block's width the field labels take.
LABEL_SHARE = 0.38
#: Line pitch, as a multiple of the type size.
LEADING = 1.50

#: Everything is laid on at just under full strength, so the type sits IN the
#: paper rather than on top of it — a solid black overprint gives a
#: program-filled sheet away at a glance, and the office asked for 85–90%.
#: The ППУ pair has read this way from the start; the translation now matches.
TEXT_OPACITY = 0.88
