"""Latin → Cyrillic transliteration for passport data.

Some passports print the holder's name in Latin (e.g. KHUDAYBERDIEV JASUR), but
the МВД form must be filled in Russian Cyrillic. The AI is asked to output
Cyrillic already; this is the deterministic safety net that converts anything
that still comes back in Latin. It is idempotent: text that is already Cyrillic
is returned unchanged.
"""

from __future__ import annotations

# Longest sequences first so digraphs win over single letters.
_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("SHCH", "Щ"), ("SCH", "Щ"),
    ("KH", "Х"), ("ZH", "Ж"), ("CH", "Ч"), ("SH", "Ш"), ("TS", "Ц"),
    ("YO", "Ё"), ("YU", "Ю"), ("YA", "Я"), ("YE", "Е"),
    ("O'", "О"), ("G'", "Г"),
)

_SINGLE: dict[str, str] = {
    "A": "А", "B": "Б", "C": "К", "D": "Д", "E": "Е", "F": "Ф", "G": "Г",
    "H": "Х", "I": "И", "J": "Ж", "K": "К", "L": "Л", "M": "М", "N": "Н",
    "O": "О", "P": "П", "Q": "К", "R": "Р", "S": "С", "T": "Т", "U": "У",
    "V": "В", "W": "В", "X": "Х", "Y": "Й", "Z": "З", "'": "", "`": "", "ʼ": "",
}


def _has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= c <= "ӿ" for c in text)


def to_cyrillic(text: str) -> str:
    """Transliterate Latin → Cyrillic. Cyrillic (or empty) input is unchanged."""
    if not text or _has_cyrillic(text):
        return text
    t = text.upper()
    out: list[str] = []
    i = 0
    n = len(t)
    while i < n:
        matched = False
        for lat, cyr in _DIGRAPHS:
            if t.startswith(lat, i):
                out.append(cyr)
                i += len(lat)
                matched = True
                break
        if matched:
            continue
        out.append(_SINGLE.get(t[i], t[i]))
        i += 1
    return "".join(out)
