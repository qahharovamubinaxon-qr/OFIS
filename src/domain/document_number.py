"""The extra digit a passport number sometimes arrives with, and its removal.

A vision model shown a passport very often reads the number off the strip at
the foot of the page rather than the printed row. Down there the nine
document characters are followed by a **check digit** — a weighted sum of the
characters before it — so «FB2254876» comes back as «FB22548766», one digit
too many, and that wrong number then goes onto a registration.

That is all this module does: take the extra digit back off, and only when
the arithmetic PROVES it belongs to the characters before it. Nothing here
reads a document, judges one, or warns about one — the office asked for no
such warnings, and there are none.
"""

from __future__ import annotations

import re

#: Weighted 7-3-1 over the characters, the way ICAO 9303 defines it.
_WEIGHTS = (7, 3, 1)


def check_digit(value: str) -> str:
    """The digit that ends ``value`` in a passport's machine strip, or "".

    Letters count from A=10, the filler «<» counts as zero, and anything
    else means this is not a strip value at all.
    """
    total = 0
    for i, char in enumerate(value):
        if char.isdigit():
            digit = int(char)
        elif char == "<":
            digit = 0
        elif char.isalpha():
            digit = ord(char.upper()) - 55
        else:
            return ""
        total += digit * _WEIGHTS[i % 3]
    return str(total % 10)


def strip_document_check_digit(document: str) -> str:
    """«FB22548766» → «FB2254876» — the trailing check digit taken back off.

    Removed only when the arithmetic proves it: the candidate must be
    letters-then-digits, ten characters long, and its last digit must be the
    check digit of the first nine.

    Digits-only documents are left alone on purpose. A Russian internal
    passport is 4+6 = ten digits with no letters, so a ten-digit number here
    is as likely to be a whole Russian passport as a Tajik one carrying a
    check digit — and one chance in ten the arithmetic would "prove" the
    wrong thing.
    """
    packed = "".join((document or "").split()).upper()
    if (len(packed) == 10 and packed[0].isalpha() and packed[-1].isdigit()
            and re.fullmatch(r"[A-Z]{1,3}\d{7,9}", packed)
            and check_digit(packed[:9]) == packed[9]):
        return packed[:9]
    return packed
