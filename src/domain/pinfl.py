"""ПИНФЛ — the fourteen digits an Uzbek passport carries in its bottom strip.

The Uzbek certificates the office sends home all name the worker by his
ПИНФЛ (ЖШШИР), and it is printed nowhere on the passport's face — only in
the strip at the foot of the page, at the end of the second line.

The office's own rule, in its own words: «пастдаги машина ўқийдиган 2
қаторнинг охиридаги 16 рақамдан 14 таси ПИНФЛ, охирги 2 таси олинмайди».
That is exactly right, and it is arithmetic, not a reading: the last two
are ICAO check digits, the fourteen before them are the number itself.

The number says the same things twice over, which is what lets it be
checked rather than believed:

    3  130195  4050087
    │  │       └── the individual's own digits
    │  └────────── the birth date, DDMMYY
    └───────────── century and sex: 1–2 born in the 1800s, 3–4 in the
                   1900s, 5–6 in the 2000s; odd is male, even is female

So a ПИНФЛ pulled out of the strip is checked against the birth date the
passport prints above it. If the two disagree, the strip was misread and
nothing is returned — a wrong ПИНФЛ on a certificate sent to the agency is
far worse than an empty box the operator fills in by hand.
"""

from __future__ import annotations

import re
from datetime import date

#: What the strip's second line ends with: the number and its check digits.
LENGTH = 14
_TAIL = 16
_DIGITS = re.compile(r"\d")

#: century digit → which hundred years the holder was born in
_CENTURY = {"1": 1800, "2": 1800, "3": 1900, "4": 1900, "5": 2000, "6": 2000}


def pinfl_from_mrz(line2: str, born: date | None = None) -> str:
    """The ПИНФЛ out of the strip's second line, or "" when it does not add up.

    ``born`` is the birth date the passport prints on its face; when it is
    given the two are made to agree, which is the whole point of reading
    the number rather than typing it.
    """
    digits = "".join(_DIGITS.findall(line2 or ""))
    if len(digits) < _TAIL:
        return ""
    found = digits[-_TAIL:][:LENGTH]
    if not is_pinfl(found):
        return ""
    if born is not None and birth_of(found) != born:
        return ""
    return found


def is_pinfl(value: str) -> bool:
    """Fourteen digits that say a century, a sex and a real date."""
    value = (value or "").strip()
    if len(value) != LENGTH or not value.isdigit():
        return False
    return value[0] in _CENTURY and birth_of(value) is not None


def birth_of(value: str) -> date | None:
    """The birth date the number carries — «3 130195 …» is 13.01.1995."""
    if len(value or "") != LENGTH or not value.isdigit():
        return None
    century = _CENTURY.get(value[0])
    if century is None:
        return None
    day, month, year = int(value[1:3]), int(value[3:5]), int(value[5:7])
    try:
        return date(century + year, month, day)
    except ValueError:
        return None


def is_male(value: str) -> bool | None:
    """Odd is male, even is female — None when the number is not one."""
    if not is_pinfl(value):
        return None
    return int(value[0]) % 2 == 1
