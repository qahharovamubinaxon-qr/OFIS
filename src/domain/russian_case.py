"""A worker's name in the case a Russian form asks for it in.

Russian forms almost never want a name as the passport prints it. «Выдано
кому?» wants the dative — «Саидову Сардору Акмаловичу». «Заявление от кого?»
wants the genitive — «от Саидова Сардора Акмаловича». Typed by hand this is
where the mistakes live, and a name spelled wrong on a migration document is
the kind of mistake that comes back.

The one rule that matters most
------------------------------
**A woman's name that ends in a consonant does not decline at all.** «Юсуф
Гулшан» is «Юсуф Гулшан» in every case — and getting this wrong is the
commonest error on these forms, because the masculine ending looks so
natural. Central Asian women's names very often end in a consonant, so this
is not an edge case here; it is half the workers.

What is handled
---------------
Surnames in -ов/-ев/-ин (the possessive kind), adjectival -ский/-ый/-ой,
plain consonant-final foreign surnames, and -а/-я surnames. Given names
ending in a consonant, -й, -ь, -а, -я. Patronymics in -ович/-евич and
-овна/-евна. The spelling rules that go with them: и after г к х ж ш щ ч
rather than ы, and е after a husher rather than о.

What is NOT handled, deliberately
---------------------------------
Nothing is invented for a shape the rules do not cover — an unusual ending
is handed back UNCHANGED rather than guessed at. A name left as the passport
prints it is a name the operator can see and fix; a name declined by
invention is one nobody notices until the form comes back.
"""

from __future__ import annotations

from src.common.logging import get_logger

log = get_logger(__name__)

#: The five cases a Russian document ever asks a name in.
CASES = ("gen", "dat", "acc", "ins", "pre")
CASE_NAMES = {
    "gen": "Родительный (кого? — от Саидова)",
    "dat": "Дательный (кому? — Саидову)",
    "acc": "Винительный (кого? — Саидова)",
    "ins": "Творительный (кем? — Саидовым)",
    "pre": "Предложный (о ком? — о Саидове)",
}

_VELAR_HUSH = "гкхжшщч"      # after these, «и» stands where «ы» would
_HUSH = "жшщч"               # after these, «е» stands where «о» would
_VOWELS = "аеёиоуыэюя"


def _ends(word: str, *tails: str) -> bool:
    low = word.lower()
    return any(low.endswith(t) for t in tails)


def _swap(word: str, cut: int, tail: str) -> str:
    """Replace the last ``cut`` letters with ``tail``, keeping the case shape."""
    stem = word[:-cut] if cut else word
    return stem + (tail.upper() if word.isupper() else tail)


# --------------------------------------------------------------- surnames
def _surname_male(word: str, case: str) -> str:
    if _ends(word, "ов", "ев", "ёв", "ин", "ын"):
        return _swap(word, 0, {"gen": "а", "dat": "у", "acc": "а",
                               "ins": "ым", "pre": "е"}[case])
    if _ends(word, "ский", "цкий", "ний"):
        return _swap(word, 2, {"gen": "ого", "dat": "ому", "acc": "ого",
                               "ins": "им", "pre": "ом"}[case])
    if _ends(word, "ый", "ой", "ий"):
        return _swap(word, 2, {"gen": "ого", "dat": "ому", "acc": "ого",
                               "ins": "ым", "pre": "ом"}[case])
    if _ends(word, "а"):
        return _a_stem(word, case, feminine_word=True)
    if _ends(word, "я"):
        return _swap(word, 1, {"gen": "и", "dat": "е", "acc": "ю",
                               "ins": "ей", "pre": "е"}[case])
    if _ends(word, "й"):
        return _swap(word, 1, {"gen": "я", "dat": "ю", "acc": "я",
                               "ins": "ем", "pre": "е"}[case])
    if _ends(word, "ь"):
        return _swap(word, 1, {"gen": "я", "dat": "ю", "acc": "я",
                               "ins": "ем", "pre": "е"}[case])
    if word and word[-1].lower() not in _VOWELS:
        # a plain consonant: Юсуф, Саид, Каримзод
        ins = "ем" if word[-1].lower() in _HUSH else "ом"
        return _swap(word, 0, {"gen": "а", "dat": "у", "acc": "а",
                               "ins": ins, "pre": "е"}[case])
    return word                                  # -о, -е, -и, -у: unchanged


def _surname_female(word: str, case: str) -> str:
    if _ends(word, "ова", "ева", "ёва", "ина", "ына"):
        # possessive: one ending for four cases, «-у» only for the accusative
        return _swap(word, 1, "у" if case == "acc" else "ой")
    if _ends(word, "ская", "цкая", "ая"):
        return _swap(word, 2, "ую" if case == "acc" else "ой")
    if _ends(word, "а"):
        return _a_stem(word, case, feminine_word=True)
    if _ends(word, "я"):
        return _swap(word, 1, {"gen": "и", "dat": "е", "acc": "ю",
                               "ins": "ей", "pre": "е"}[case])
    # A woman's surname ending in a consonant does NOT decline. Neither does
    # one ending in any other vowel.
    return word


def _a_stem(word: str, case: str, feminine_word: bool) -> str:
    """A word in «-а»: Кучма, Гулнора, Никита — all decline the same way."""
    before = word[-2].lower() if len(word) >= 2 else ""
    gen = "и" if before in _VELAR_HUSH else "ы"
    ins = "ей" if before in _HUSH else "ой"
    return _swap(word, 1, {"gen": gen, "dat": "е", "acc": "у",
                           "ins": ins, "pre": "е"}[case])


# ------------------------------------------------------------ given names
def _name_male(word: str, case: str) -> str:
    if _ends(word, "а"):
        return _a_stem(word, case, feminine_word=False)
    if _ends(word, "я"):
        return _swap(word, 1, {"gen": "и", "dat": "е", "acc": "ю",
                               "ins": "ей", "pre": "е"}[case])
    if _ends(word, "й"):
        return _swap(word, 1, {"gen": "я", "dat": "ю", "acc": "я",
                               "ins": "ем", "pre": "е"}[case])
    if _ends(word, "ь"):
        return _swap(word, 1, {"gen": "я", "dat": "ю", "acc": "я",
                               "ins": "ем", "pre": "е"}[case])
    if word and word[-1].lower() not in _VOWELS:
        ins = "ем" if word[-1].lower() in _HUSH else "ом"
        return _swap(word, 0, {"gen": "а", "dat": "у", "acc": "а",
                               "ins": ins, "pre": "е"}[case])
    return word


def _name_female(word: str, case: str) -> str:
    if _ends(word, "ия"):
        return _swap(word, 1, {"gen": "и", "dat": "и", "acc": "ю",
                               "ins": "ей", "pre": "и"}[case])
    if _ends(word, "я"):
        return _swap(word, 1, {"gen": "и", "dat": "е", "acc": "ю",
                               "ins": "ей", "pre": "е"}[case])
    if _ends(word, "а"):
        return _a_stem(word, case, feminine_word=True)
    if _ends(word, "ь"):
        return _swap(word, 1, {"gen": "и", "dat": "и", "acc": "ь",
                               "ins": "ью", "pre": "и"}[case])
    # …and a consonant-final woman's name stays exactly as it is.
    return word


# ------------------------------------------------------------ patronymics
def _patronymic(word: str, case: str, male: bool) -> str:
    if male and _ends(word, "ович", "евич", "ич"):
        return _swap(word, 0, {"gen": "а", "dat": "у", "acc": "а",
                               "ins": "ем", "pre": "е"}[case])
    if not male and _ends(word, "овна", "евна", "ична", "инична"):
        return _swap(word, 1, {"gen": "ы", "dat": "е", "acc": "у",
                               "ins": "ой", "pre": "е"}[case])
    # Tajik and Uzbek patronymics («угли», «кизи», «оглы») do not decline
    return _name_male(word, case) if male else _name_female(word, case)


# ------------------------------------------------------------------ public
def decline(word: str, case: str, *, male: bool = True,
            kind: str = "name") -> str:
    """One word in ``case``. Unchanged when the rules do not cover its shape."""
    word = (word or "").strip()
    if not word or case not in CASES:
        return word
    if "-" in word:                               # Абдулла-Хан, Кара-оглы
        return "-".join(decline(part, case, male=male, kind=kind)
                        for part in word.split("-"))
    if kind == "surname":
        return _surname_male(word, case) if male else _surname_female(word, case)
    if kind == "patronymic":
        return _patronymic(word, case, male)
    return _name_male(word, case) if male else _name_female(word, case)


def decline_fio(surname: str, name: str, patronymic: str, case: str, *,
                male: bool = True) -> str:
    """«Саидов Сардор Акмалович» → «Саидову Сардору Акмаловичу»."""
    parts = (
        decline(surname, case, male=male, kind="surname"),
        decline(name, case, male=male, kind="name"),
        decline(patronymic, case, male=male, kind="patronymic"),
    )
    return " ".join(p for p in parts if p)


__all__ = ["CASES", "CASE_NAMES", "decline", "decline_fio"]
