"""Latin → Cyrillic transliteration for passport data.

Some passports print the holder's name in Latin (e.g. KHUDAYBERDIEV JASUR), but
the МВД form must be filled in Russian Cyrillic. The AI is asked to output
Cyrillic already; this is the deterministic safety net that converts anything
that still comes back in Latin.

Cyrillic is not simply passed through: a Tajik passport prints its holder in
Cyrillic too, only in the Tajik alphabet — Ҷ ҷ Ҳ ҳ Қ қ Ғ ғ Ӣ ӣ Ӯ ӯ — and a
Russian form has no such letters. Whatever this is given comes back in
RUSSIAN letters (Хоҷа → Ходжа), which is what the office asked for
everywhere in the program.
"""

from __future__ import annotations

from src.domain.passport_rules import in_russian_letters, issuer_in_russian

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
    """Latin → Cyrillic, and Cyrillic → RUSSIAN Cyrillic. Empty is unchanged."""
    if not text:
        return text
    if _has_cyrillic(text):
        return in_russian_letters(text)
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
    return in_russian_letters("".join(out))


def translate_issuer(value: str) -> str:
    """«Кем выдан» → its Russian equivalent (MIA 4102 → МВД 4102, ХШБ ВКД ҶТ →
    МВД РТ). Applied before transliteration so codes are not mangled.

    The dictionary itself lives in :mod:`src.domain.passport_rules`: which
    office a passport names is the form's business, not the reader's, and the
    same translation has to happen for a passport typed in by hand.
    """
    return issuer_in_russian(value)
