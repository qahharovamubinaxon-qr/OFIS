"""How a foreign passport must read once it is on a Russian form.

Two office rules, kept here rather than in any one section so that every
document the program fills obeys them — the МВД forms, the трудовой договор,
the уведомление, ДМС, бейджик, свера, all of them.

**A Tajik passport has no серия.** It carries one nine-digit number that starts
with a 4 — «406576690». What the passport does print beside it is the country
code, «TJK», and reading that as the серия produced «TJK406576690» on every
form: a number that belongs to nobody. The серия box is left empty and only the
nine digits are written.

**«Кем выдан» is written in Russian.** A Tajik passport names its issuing
office in Tajik — «ХШБ ВКД ҶТ» — and a Russian form may not. The abbreviations
the office's workers actually carry are translated (ХШБ → МВД, ҶТ → РТ,
ФР → РФ), and whatever is left keeps its meaning but loses the six letters
Tajik has and Russian does not (ҳ қ ғ ӣ ӯ ҷ). The vision model is asked for
Russian too; this is the deterministic net under it, so a passport read on a
day the model was careless still comes out right.
"""

from __future__ import annotations

import re

#: A country code is never a серия — it is the state that issued the passport.
_COUNTRY_CODES = frozenset({
    "TJK", "UZB", "KGZ", "KAZ", "TKM", "AZE", "ARM", "GEO", "MDA", "UKR",
    "BLR", "RUS", "ТЖК", "УЗБ", "РУС",
})

#: However the citizenship reached the model — from the machine-readable zone,
#: from the vision model, or typed by the operator.
_TAJIK = ("ТАДЖИКИСТАН", "ТОДЖИКИСТОН", "ТОЧИКИСТОН", "ТОҶИКИСТОН",
          "TAJIKISTAN", "TJK", "ТЖК")

#: «406576690» — nine digits, the first of them a 4.
_TAJIK_NUMBER = re.compile(r"4\d{8}")
#: «TJK406576690» — the code run into the number by whoever read it.
_CODE_THEN_NUMBER = re.compile(r"^([A-ZА-Я]{2,3})[\s-]*(\d{6,})$")

#: Back out of Cyrillic, for the серия only.
#:
#: A passport серия is **never** translated — «FA», «FB», «C» are printed in
#: Latin and go onto the Russian form in Latin, exactly as printed. But the
#: reader is told to write everything else in Russian, and on a careless day it
#: carries the серия across too, which turns «FA» into «ФА» — a серия that
#: belongs to no passport in the world.
#:
#: The look-alikes come first, because a reader that converts a серия nearly
#: always converts what it *sees*: Cyrillic С is Latin C, Н is H, Р is P, У is
#: Y, Х is X. The rest of the alphabet has no twin to be confused with, so
#: those fall back to the sound — Ф is F, Г is G, Ж is J.
_SERIES_BACK = {
    # the twelve that look the same in both alphabets
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
    "О": "O", "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X",
    # and the rest, by sound
    "Б": "B", "Г": "G", "Д": "D", "Ж": "J", "З": "Z", "И": "I", "Й": "I",
    "Л": "L", "П": "P", "Ф": "F", "Ц": "C", "Ч": "C", "Ш": "S", "Щ": "S",
    "Ы": "Y", "Э": "E", "Ю": "U", "Я": "A", "Ь": "", "Ъ": "",
    # foreign twins, so a Tajik or Ukrainian reading lands somewhere sane
    "Ҳ": "X", "Қ": "K", "Ғ": "G", "Ӣ": "I", "Ӯ": "Y", "Ө": "O", "Ү": "Y",
    "Ң": "H", "І": "I", "Ї": "I", "Є": "E", "Ґ": "G", "Ҷ": "J",
}


def series_in_latin(series: str | None) -> str:
    """The серия as the passport prints it: Latin, never translated.

    Digits pass through untouched — a Russian internal passport's «4512» is a
    серия too. Anything already in Latin is returned as it stands, so this can
    be run over every passport without asking where it came from.
    """
    value = re.sub(r"[\s-]+", "", (series or "")).upper()
    if not value:
        return ""
    return "".join(_SERIES_BACK.get(ch, ch) for ch in value)


def is_tajik(nationality: str | None) -> bool:
    value = (nationality or "").strip().upper().replace("Ё", "Е")
    return any(value.startswith(name[:6]) for name in _TAJIK) if value else False


def normalise_document(series: str | None, number: str | None,
                       nationality: str | None = None) -> tuple[str | None, str]:
    """The серия and номер as they must be written on a Russian form.

    Whatever the passport was read by, a country code never survives as a
    серия, and a Tajik passport keeps its nine digits and nothing else.
    """
    series = re.sub(r"\s+", "", (series or "")).upper()
    number = (number or "").strip()

    if series in _COUNTRY_CODES:
        tajik = is_tajik(series) or is_tajik(nationality)
        series = ""
    else:
        tajik = is_tajik(nationality)

    head = _CODE_THEN_NUMBER.match(number.upper().replace(" ", ""))
    if head is not None and head.group(1) in _COUNTRY_CODES:
        tajik = tajik or is_tajik(head.group(1))
        number = head.group(2)

    if tajik:
        digits = re.sub(r"\D", "", number)
        found = _TAJIK_NUMBER.search(digits)
        number = found.group(0) if found else digits
        series = ""

    # last, so the country-code and Tajik rules have already had their say:
    # whatever серия survives is written the way the passport prints it. The
    # номер gets the same treatment, because a серия the reader glued onto the
    # front of it would otherwise carry the Cyrillic in by the back door.
    series = series_in_latin(series)
    if any(ch.isalpha() for ch in number):
        number = series_in_latin(number)
    return (series or None), number


# ------------------------------------------------------------ кем выдан

#: Letters the neighbouring alphabets have and Russian does not. Tajik «ҷ» is
#: the one that is not a letter swap at all — it is «дж»: Ҷумҳурӣ is Джумхури,
#: Тоҷикистон is Таджикистан. The rest drop to their nearest Russian letter.
#: Latin scripts are not here; they are transliterated by the reader.
_FOREIGN_OUT = {
    # Tajik
    "Ҳ": "Х", "ҳ": "х", "Қ": "К", "қ": "к", "Ғ": "Г", "ғ": "г",
    "Ӣ": "И", "ӣ": "и", "Ӯ": "У", "ӯ": "у",
    # Kyrgyz
    "Ө": "О", "ө": "о", "Ү": "У", "ү": "у", "Ң": "Н", "ң": "н",
    # Ukrainian
    "І": "И", "і": "и", "Ї": "И", "ї": "и", "Є": "Е", "є": "е",
    "Ґ": "Г", "ґ": "г",
}

#: For *matching* only, each Russian letter stands for itself or its foreign
#: twin — «ҶТ» and «ЧТ» are the same republic, «СГІРФО» and «СГИРФО» the same
#: sector — so one entry covers however the document spelled it.
_TWINS = {
    "Х": "ХҲ", "К": "КҚ", "Г": "ГҒҐ", "И": "ИӢІЇ", "У": "УӮҮ",
    "Ч": "ЧҶ", "О": "ОӨ", "Н": "НҢ", "Е": "ЕЄ",
}

#: «Кем выдан», as the office's own reference table gives it: the issuing body
#: written the way a Russian form writes it — by its **initials**, in capitals.
#:
#: Longest first, always: «ХШБ РВКД» has to win over «ХШБ ВКД», which has to
#: win over «ХШБ» and «ВКД» separately.
#:
#: This is the *guarantee*, not the whole translation. There is one of these
#: for every district office in every country the workers come from, and no
#: hand-written list will ever hold them all — the vision model is asked to
#: work the rest out itself and write the Russian. What it does not resolve
#: still comes through here readable and in Russian letters, never invented.
_PHRASES: tuple[tuple[str, str], ...] = (
    # ---- Тоҷикистон
    #
    # A Tajik passport prints its issuing office in Latin as «MIA 14505» —
    # the ministry and the office's own number. That is what the office
    # writes on its forms: «МВД 14505». Whatever the page spells the same
    # office out as (ХШБ ВКД, the full Tajik phrase, the passport service
    # by name) is that one office, so it comes out «МВД» too and the number
    # beside it survives untouched. The duplicate-word rule at the end of
    # :func:`issuer_in_russian` collapses «МВД МВД» back to one.
    ("ХАДАМОТИ ШИНОСНОМАВИЮ БАКАЙДГИРИИ РАЕСАТИ ВАЗОРАТИ КОРХОИ ДОХИЛИ",
     "МВД"),
    ("ХАДАМОТИ ШИНОСНОМАВИЮ БАКАЙДГИРИИ ВАЗОРАТИ КОРХОИ ДОХИЛИ", "МВД"),
    ("ХАДАМОТИ ШИНОСНОМАВИЮ БАКАЙДГИРИИ", "МВД"),
    ("ШУЪБАИ ВАЗОРАТИ КОРХОИ ДОХИЛИ", "МВД"),
    ("ВАЗОРАТИ КОРХОИ ДОХИЛИИ", "МВД"),
    ("ВАЗОРАТИ КОРХОИ ДОХИЛИ", "МВД"),
    ("ЧУМХУРИИ ТОЧИКИСТОН", "РТ"),
    ("ФЕДЕРАТСИЯИ РУСИЯ", "РФ"),
    ("ФЕДЕРАТСИЯИ РОССИЯ", "РФ"),
    ("ТОЧИКИСТОН", "ТАДЖИКИСТАН"),
    ("ХШБ РВКД", "МВД"),
    ("ХШБ ВКД", "МВД"),
    ("ШВКД", "МВД"),
    ("ХШБ", "МВД"),
    ("ВКД", "МВД"),
    ("ПРС УМВД", "МВД"),
    ("ПРС МВД", "МВД"),
    ("ПРС", "МВД"),
    ("ЧТ", "РТ"),
    ("ФР", "РФ"),
    ("ДАР", "в"),          # «ХШБ дар Душанбе» → «ПРС в Душанбе»
    # ---- Кыргызстан
    ("САНАРИПТИК ОНУКТУРУУ МИНИСТРЛИГИ", "МЦР"),
    ("МАМЛЕКЕТТИК КАТТОО КЫЗМАТЫ", "ГРС"),
    ("STATE AGENCY FOR INFORMATION RESOURCES AND TECHNOLOGY", "ГАИРТ"),
    ("MINISTRY OF DIGITAL DEVELOPMENT", "МЦР"),
    ("STATE REGISTRATION SERVICE", "ГРС"),
    ("SAIRT", "ГАИРТ"), ("MDD", "МЦР"), ("SRS", "ГРС"),
    ("СОМ", "МЦР"), ("МКК", "ГРС"),
    # ---- Ўзбекистон
    ("ICHKI ISHLAR VAZIRLIGI", "МВД"),
    ("ICHKI ISHLAR BOSHQARMASI", "УВД"),
    ("DAVLAT XIZMATLARI MARKAZI", "ЦГУ"),
    ("TRIB", "МРЭО"), ("YHXB", "УБДД"),
    ("IIV", "МВД"), ("IIB", "УВД"), ("PSC", "ЦГУ"),
    # ---- Україна
    ("СГИРФО", "СГИРФО"), ("ВГИРФО", "ВГИРФО"),
    ("МРЕВ", "МРЭО"), ("ВРЕР", "ОРЭР"),
    # ---- Moldova
    ("AGENTIA SERVICII PUBLICE", "АОУ"),
    ("ASP", "АОУ"), ("CRIS", "ЦГИР"), ("REGISTRU", "Регистру"),
    # ---- the rest, as they were already known
    ("MINISTRY OF JUSTICE OF GEORGIA", "Министерство юстиции Грузии"),
    ("MINISTRY OF INTERNAL AFFAIRS", "МВД"),
    ("DEPARTMENT OF INTERNAL AFFAIRS", "ОВД"),
    ("MIA", "МВД"), ("MVD", "МВД"), ("DIA", "ОВД"),
    ("MFA", "МИД"), ("SSD", "ГСД"),
)


def _either_alphabet(word: str) -> str:
    """A pattern matching ``word`` however its Tajik letters were typed."""
    out = []
    for char in word:
        twins = _TWINS.get(char.upper())
        out.append(f"[{twins}{twins.lower()}]" if twins else re.escape(char))
    return "".join(out)


_COMPILED = tuple((re.compile(rf"\b{_either_alphabet(src)}\b", re.IGNORECASE), ru)
                  for src, ru in _PHRASES)


def _in_russian_letters(text: str) -> str:
    """Whatever no entry claimed, spelled the way Russian spells it."""
    out: list[str] = []
    for i, char in enumerate(text):
        if char in ("Ҷ", "ҷ"):
            after = text[i + 1] if i + 1 < len(text) else ""
            if char == "ҷ":
                out.append("дж")
            else:
                out.append("ДЖ" if after.isupper() or not after.isalpha()
                           else "Дж")
            continue
        out.append(_FOREIGN_OUT.get(char, char))
    return "".join(out)


def issuer_in_russian(value: str | None) -> str:
    """«ХШБ ВКД ҶТ» → «МВД РТ». Text already in Russian comes back unchanged."""
    out = value or ""
    for pattern, russian in _COMPILED:
        out = pattern.sub(russian, out)
    out = _in_russian_letters(out)
    # «ХШБ ВКД ҶТ» is one office named twice over, not two — writing «МВД МВД»
    # would put a department on the form that does not exist
    out = re.sub(r"\b(\S+)(\s+\1\b)+", r"\1", out)
    return re.sub(r"\s+", " ", out).strip()
