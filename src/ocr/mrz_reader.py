"""The two lines at the foot of a passport — and the arithmetic that proves them.

The machine-readable zone carries the surname, the given names, the document
number, the date of birth, the sex and the expiry date, and — this is the point —
a **check digit** beside each of them. The digits are a weighted sum of the
characters they follow, so a value that was misread almost never adds up.

That makes the MRZ the one part of a passport that can be *proved* rather than
believed. When the arithmetic holds, these values are taken over whatever the
vision model said about the same passport; when it does not, nothing is
overwritten and the operator is told to look at the document themselves. A
quietly wrong passport number is far worse than a visible warning.

No API and no key is involved: the OCR text is already in hand, and everything
after that is arithmetic done here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from src.common.logging import get_logger
from src.ocr.translit import to_cyrillic

log = get_logger(__name__)

#: TD3 is the passport booklet (2×44); TD2 is the smaller card (2×36).
LENGTHS = (44, 36)
_MRZ_CHARS = re.compile(r"^[A-Z0-9<]+$")
_FILLER = re.compile(r"<+")


@dataclass(frozen=True)
class MrzResult:
    """What the machine-readable zone says, and whether it proved itself."""

    found: bool = False
    valid: bool = False
    lines: tuple[str, str] | None = None
    fields: dict[str, str] = field(default_factory=dict)
    problems: tuple[str, ...] = ()

    @property
    def trusted(self) -> bool:
        """True only when every check digit added up — the licence to override."""
        return self.found and self.valid


# ------------------------------------------------------------------ finding


def _candidate(line: str) -> str:
    """One OCR line, squeezed into what an MRZ line would look like.

    Scanners and vision models like to put spaces between the groups, and to
    read the filler «<» as «K» or ««». Both are undone here; anything else is
    left alone so a wrong line simply fails to match.
    """
    text = line.strip().upper().replace(" ", "").replace("«", "<").replace("‹", "<")
    return text.replace("КК", "<<")


def find_lines(text: str) -> tuple[str, str] | None:
    """The two MRZ lines inside a page of OCR text, or None.

    Handles the two ways OCR delivers them: as two lines, or as one long run
    when the reader joined them.
    """
    if not text:
        return None
    rows = [_candidate(row) for row in text.splitlines()]
    rows = [r for r in rows if r and _MRZ_CHARS.fullmatch(r)]

    for size in LENGTHS:
        for i in range(len(rows) - 1):
            if len(rows[i]) == size and len(rows[i + 1]) == size:
                return rows[i], rows[i + 1]
        # both halves on one line
        for row in rows:
            if len(row) == size * 2:
                return row[:size], row[size:]
    return None


def _pair(line1: str, line2: str) -> tuple[str, str] | None:
    """Two lines the caller supplied directly (a model can read them off)."""
    first, second = _candidate(line1), _candidate(line2)
    if not (_MRZ_CHARS.fullmatch(first) and _MRZ_CHARS.fullmatch(second)):
        return None
    if len(first) != len(second) or len(first) not in LENGTHS:
        return None
    return first, second


# ------------------------------------------------------------------ reading


def read(text: str = "", *, line1: str = "", line2: str = "") -> MrzResult:
    """Find the zone, check its arithmetic, and return what it says.

    ``line1``/``line2`` are used when the reader already separated them;
    otherwise the lines are located inside ``text``.
    """
    lines = _pair(line1, line2) if (line1 and line2) else None
    if lines is None:
        lines = find_lines(text)
    if lines is None:
        return MrzResult(found=False)

    joined = "\n".join(lines)
    try:
        checker = _checker(len(lines[0]))(joined, check_expiry=False)
    except Exception as exc:  # noqa: BLE001 - a malformed zone is not a crash
        log.info("MRZ not readable: %s", str(exc)[:120])
        return MrzResult(found=True, lines=lines,
                         problems=(f"MRZ ўқилмади: {str(exc)[:80]}",))

    valid = bool(checker)
    problems = () if valid else _problems(lines)
    if not valid:
        log.info("MRZ check digits do not add up: %s", "; ".join(problems))
        return MrzResult(found=True, valid=False, lines=lines, problems=problems)

    return MrzResult(found=True, valid=True, lines=lines,
                     fields=_translate(checker.fields()))


def _checker(size: int):
    if size == 36:
        from mrz.checker.td2 import TD2CodeChecker

        return TD2CodeChecker
    from mrz.checker.td3 import TD3CodeChecker

    return TD3CodeChecker


#: Weighted 7-3-1 over the characters, the way ICAO 9303 defines it. Worked out
#: here rather than read off the library's report so the operator is told which
#: field is wrong, not merely that something is.
_WEIGHTS = (7, 3, 1)


def check_digit(value: str) -> str:
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


def _problems(lines: tuple[str, str]) -> tuple[str, ...]:
    """Exactly which fields do not add up, in words the operator can act on."""
    second = lines[1]
    spans = ((0, 9, 9, "паспорт рақами"),
             (13, 19, 19, "туғилган сана"),
             (21, 27, 27, "амал муддати"))
    out = [label for start, end, at, label in spans
           if len(second) > at and check_digit(second[start:end]) != second[at]]
    return tuple(out) or ("умумий назорат рақами мос келмади",)


# -------------------------------------------------------------- translating


def _translate(f) -> dict[str, str]:
    """The zone's own values, in the shape the passport model wants."""
    names = _FILLER.sub(" ", f.name or "").split()
    document = (f.document_number or "").replace("<", "")
    series, number = _split_number(document)
    out = {
        "surname": to_cyrillic(_FILLER.sub(" ", f.surname or "").strip()),
        "name": to_cyrillic(names[0]) if names else "",
        "patronymic": to_cyrillic(" ".join(names[1:])) if len(names) > 1 else "",
        "series": series,
        "number": number,
        "nationality": _country((f.nationality or "").replace("<", "")),
        "gender": {"M": "male", "F": "female"}.get((f.sex or "").upper(), ""),
    }
    birth = _date(f.birth_date, future=False)
    expiry = _date(f.expiry_date, future=True)
    if birth:
        out["birth_date"] = birth.isoformat()
    if expiry:
        out["expiry_date"] = expiry.isoformat()
    return {k: v for k, v in out.items() if v}


_SERIES = re.compile(r"^([A-Z]{1,3})(\d{5,9})$")


def strip_document_check_digit(document: str) -> str:
    """«FB22548766» → «FB2254876» — the MRZ check digit taken back off.

    A vision model shown a passport often reads the number off the machine
    zone, where the document field is nine characters **followed by its check
    digit** — and hands back both, one digit too many. The extra digit is only
    removed when the arithmetic PROVES it: the candidate must be a
    letters-then-digits document of ten characters whose last digit is the
    ICAO check digit of the first nine.

    Digits-only documents are left alone on purpose. A Russian internal
    passport is 4+6 = ten digits with no letters, so a ten-digit number here is
    as likely to be a whole Russian passport as a Tajik one with a check digit
    — and one chance in ten the arithmetic would "prove" the wrong thing.
    """
    packed = "".join((document or "").split()).upper()
    if (len(packed) == 10 and packed[0].isalpha() and packed[-1].isdigit()
            and re.fullmatch(r"[A-Z]{1,3}\d{7,9}", packed)
            and check_digit(packed[:9]) == packed[9]):
        return packed[:9]
    return packed

#: The citizenships this office actually sees, as the МВД forms spell them.
_COUNTRIES = {
    "UZB": "УЗБЕКИСТАН", "TJK": "ТАДЖИКИСТАН", "KGZ": "КИРГИЗИЯ",
    "KAZ": "КАЗАХСТАН", "TKM": "ТУРКМЕНИСТАН", "AZE": "АЗЕРБАЙДЖАН",
    "ARM": "АРМЕНИЯ", "GEO": "ГРУЗИЯ", "MDA": "МОЛДОВА", "UKR": "УКРАИНА",
    "BLR": "БЕЛАРУСЬ", "RUS": "РОССИЯ",
}


def _split_number(document: str) -> tuple[str, str]:
    """«FB1234567» → («FB», «1234567») — the app keeps the two apart."""
    m = _SERIES.fullmatch(document)
    return (m.group(1), m.group(2)) if m else ("", document)


def _country(code: str) -> str:
    """«UZB» → «УЗБЕКИСТАН». An unknown code is left as the zone printed it."""
    return _COUNTRIES.get(code.upper(), code)


def _date(yymmdd: str, *, future: bool) -> date | None:
    """«040222» → 2004-02-22. A birth date is past, an expiry is ahead."""
    digits = (yymmdd or "").strip()
    if len(digits) != 6 or not digits.isdigit():
        return None
    year, month, day = int(digits[:2]), int(digits[2:4]), int(digits[4:])
    today = date.today()
    if future:
        century = 2000
    else:
        century = 2000 if 2000 + year <= today.year else 1900
    try:
        return date(century + year, month, day)
    except ValueError:
        return None
