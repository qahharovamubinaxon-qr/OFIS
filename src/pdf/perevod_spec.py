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
#: (left, top, right, bottom) shares of the page. The copy is printed at its
#: REAL size (see :data:`REAL_MM`) and centred in here; the window is only the
#: limit it may not grow past, not the size it is stretched to.
#:
#: Wide on purpose: two open passport spreads are 250 mm of paper before the gap,
#: and on a 297 mm sheet anything tighter than this would shrink them off life
#: size. A single document, or a card's two sides, then always comes out exact.
SCAN_BOX = (0.07, 0.07, 0.93, 0.93)

#: One millimetre in points.
MM = 72.0 / 25.4

#: A gap between two originals stacked on the sheet, in millimetres.
SCAN_GAP_MM = 8.0

#: How big each document really is, in millimetres — (long side, short side).
#: A translation is read next to the original, so the copy has to LOOK like the
#: document: a passport page printed the size of half an A4 reads as a forgery of
#: something else. These are the standard sizes the documents are made in.
#:
#: * ID-1 (ISO/IEC 7810) — every plastic card: driving licence, patent card,
#:   internal ID. 85.6 × 54 mm.
#: * ID-3 — a passport booklet page, 88 × 125 mm; photographed open, the spread
#:   is twice as wide, 176 × 125 mm. Which one it is comes from the photo's own
#:   proportions, not from the operator.
#: * CIS certificates (birth, marriage) are A5, diplomas and аттестаты A4.
ID1_MM = (85.6, 54.0)
PASSPORT_PAGE_MM = (125.0, 88.0)
PASSPORT_SPREAD_MM = (176.0, 125.0)
A5_MM = (210.0, 148.0)
A4_MM = (297.0, 210.0)

REAL_MM: dict[str, tuple[float, float]] = {
    "passport": PASSPORT_PAGE_MM,
    "driver_license": ID1_MM,
    "migration_card": (148.0, 105.0),
    "birth_certificate": A5_MM,
    "marriage_certificate": A5_MM,
    "diploma": A4_MM,
    "attestat": A4_MM,
    "other": A5_MM,
}

#: Above this width-to-height ratio a passport photo is an OPEN spread rather
#: than a single page. A single ID-3 page is 0.70 wide for its height, a spread
#: 1.41 — nothing else is near 1.05.
SPREAD_ASPECT = 1.05

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
