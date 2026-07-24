"""Russian dative-case declension for ФИО (кому выдано).

The СФЕРА удостоверение addresses the holder in the dative case, e.g.
``РАСУЛОВ АЗИЗ АНВАРОВИЧ`` → ``Расулову Азизу Анваровичу``. Central-Asian
patronymics that end in «угли/оглы/кызы/…» do not take a Russian ending.

Rule-based (no dictionary): handles the common masculine forms migrants have
(surnames -ов/-ев/-ин, given names ending in a consonant/-й, patronymics
-ович/-евич) plus reasonable feminine forms. Anything it cannot classify is
returned unchanged, so it never corrupts a name — worst case it stays nominative.
"""

from __future__ import annotations

# Patronymic tails that are NOT Russian and must be left as-is.
_FOREIGN_PATRONYMIC = ("угли", "уғли", "оглы", "оглу", "кызы", "кизи", "қизи", "уулу")

_VOWELS = "аеёиоуыэюя"


def _cap(word: str) -> str:
    return word[:1].upper() + word[1:].lower() if word else word


def _dative_surname(s: str) -> str:
    low = s.lower()
    if low.endswith(("ов", "ев", "ёв", "ин", "ын")):
        return s + "у"
    if low.endswith(("ский", "цкий", "ской")):
        return s[:-2] + "ому"
    if low.endswith("ова") or low.endswith("ева") or low.endswith("ина"):
        return s[:-1] + "ой"  # feminine
    if low.endswith(("а",)) and low[-2:-1] not in "иы":
        return s[:-1] + "е"
    if low[-1] in "оеиуыэюё":  # indeclinable foreign endings
        return s
    if low[-1] not in _VOWELS:  # consonant → masculine
        return s + "у"
    return s


def _dative_given(n: str) -> str:
    low = n.lower()
    if low.endswith("ий"):
        return n[:-2] + "ию"
    if low.endswith("й"):
        return n[:-1] + "ю"
    if low.endswith("ия"):
        return n[:-2] + "ии"  # feminine
    if low.endswith("ья"):
        return n[:-1] + "е"
    if low.endswith("а"):
        return n[:-1] + "е"
    if low.endswith("я"):
        return n[:-1] + "е"
    if low[-1] in "оеиуыэюё":
        return n
    if low[-1] not in _VOWELS:
        return n + "у"
    return n


def _dative_patronymic(p: str) -> str:
    low = p.lower().replace("’", "").replace("'", "")
    if any(low.endswith(t) for t in _FOREIGN_PATRONYMIC):
        return p  # «… угли/кызы» — not declined
    if low.endswith(("ович", "евич", "ич")):
        return p + "у"
    if low.endswith(("овна", "евна", "ична", "инична")):
        return p[:-1] + "е"
    if low[-1] not in _VOWELS:
        return p + "у"
    return p


def to_dative_parts(surname: str, name: str, patronymic: str | None = None) -> list[str]:
    """Title-case dative ФИО as separate parts [Фамилии, Имени, Отчеству]."""
    parts: list[str] = []
    if surname:
        parts.append(_cap(_dative_surname(surname.strip())))
    if name:
        parts.append(_cap(_dative_given(name.strip())))
    if patronymic and patronymic.strip():
        parts.append(_cap(_dative_patronymic(patronymic.strip())))
    return parts


def to_dative(surname: str, name: str, patronymic: str | None = None) -> str:
    """Return «Фамилии Имени Отчеству» in Title-case dative, joined by spaces."""
    return " ".join(to_dative_parts(surname, name, patronymic))
