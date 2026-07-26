"""Russian numbers and dates written out in words (пропись).

Notarial documents spell out dates and amounts: «двадцать шестое июля две
тысячи двадцать шестого года», «десять тысяч рублей 00 копеек». This module
does that offline and deterministically — no AI involved.
"""

from __future__ import annotations

from datetime import date

# -- cardinals -------------------------------------------------------------

_ONES_M = ("", "один", "два", "три", "четыре", "пять", "шесть", "семь",
           "восемь", "девять")
_ONES_F = ("", "одна", "две", "три", "четыре", "пять", "шесть", "семь",
           "восемь", "девять")
_TEENS = ("десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
          "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать",
          "девятнадцать")
_TENS = ("", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят",
         "семьдесят", "восемьдесят", "девяносто")
_HUNDREDS = ("", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот",
             "семьсот", "восемьсот", "девятьсот")

# (singular, few, many) for each 1000^n group
_SCALES = (
    ("", "", "", "m"),
    ("тысяча", "тысячи", "тысяч", "f"),
    ("миллион", "миллиона", "миллионов", "m"),
    ("миллиард", "миллиарда", "миллиардов", "m"),
    ("триллион", "триллиона", "триллионов", "m"),
)


def plural(n: int, one: str, few: str, many: str) -> str:
    """Pick the Russian plural form for ``n`` (11–14 always take ``many``)."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def _triplet(value: int, feminine: bool) -> list[str]:
    """0–999 as words."""
    out: list[str] = []
    hundreds, rest = divmod(value, 100)
    if hundreds:
        out.append(_HUNDREDS[hundreds])
    tens, ones = divmod(rest, 10)
    if tens == 1:
        out.append(_TEENS[ones])
    else:
        if tens:
            out.append(_TENS[tens])
        if ones:
            out.append((_ONES_F if feminine else _ONES_M)[ones])
    return out


def number_to_words(value: int, *, feminine: bool = False) -> str:
    """Cardinal number in words: 10000 → «десять тысяч»."""
    if value == 0:
        return "ноль"
    negative = value < 0
    value = abs(value)

    groups: list[int] = []
    while value:
        value, rem = divmod(value, 1000)
        groups.append(rem)

    words: list[str] = []
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if not group:
            continue
        one, few, many, gender = _SCALES[index] if index < len(_SCALES) else ("", "", "", "m")
        is_fem = gender == "f" or (index == 0 and feminine)
        words += _triplet(group, is_fem)
        if index:
            words.append(plural(group, one, few, many))
    text = " ".join(w for w in words if w)
    return ("минус " + text) if negative else text


# -- ordinals (for dates) --------------------------------------------------

_ORD_NEUTER = {
    1: "первое", 2: "второе", 3: "третье", 4: "четвёртое", 5: "пятое",
    6: "шестое", 7: "седьмое", 8: "восьмое", 9: "девятое", 10: "десятое",
    11: "одиннадцатое", 12: "двенадцатое", 13: "тринадцатое",
    14: "четырнадцатое", 15: "пятнадцатое", 16: "шестнадцатое",
    17: "семнадцатое", 18: "восемнадцатое", 19: "девятнадцатое",
    20: "двадцатое", 30: "тридцатое",
}
_ORD_GEN_M = {
    1: "первого", 2: "второго", 3: "третьего", 4: "четвёртого", 5: "пятого",
    6: "шестого", 7: "седьмого", 8: "восьмого", 9: "девятого", 10: "десятого",
    11: "одиннадцатого", 12: "двенадцатого", 13: "тринадцатого",
    14: "четырнадцатого", 15: "пятнадцатого", 16: "шестнадцатого",
    17: "семнадцатого", 18: "восемнадцатого", 19: "девятнадцатого",
    20: "двадцатого", 30: "тридцатого", 40: "сорокового", 50: "пятидесятого",
    60: "шестидесятого", 70: "семидесятого", 80: "восьмидесятого",
    90: "девяностого",
}
_MONTHS_GEN = ("", "января", "февраля", "марта", "апреля", "мая", "июня",
               "июля", "августа", "сентября", "октября", "ноября", "декабря")


def day_to_words(day: int) -> str:
    """Day of month as a neuter ordinal: 26 → «двадцать шестое»."""
    if day in _ORD_NEUTER:
        return _ORD_NEUTER[day]
    tens, ones = divmod(day, 10)
    return f"{_TENS[tens]} {_ORD_NEUTER[ones]}".strip()


def _year_ordinal_genitive(year: int) -> str:
    """Year as a masculine genitive ordinal: 2026 → «две тысячи двадцать шестого»."""
    thousands, rest = divmod(year, 1000)
    if rest == 0:  # 2000 → «двухтысячного»
        prefix = {1: "тысячного", 2: "двухтысячного", 3: "трёхтысячного"}
        return prefix.get(thousands, number_to_words(year) + "го")

    head = " ".join(
        _triplet(thousands, feminine=True)
        + [plural(thousands, "тысяча", "тысячи", "тысяч")]
    )
    hundreds, tail = divmod(rest, 100)
    parts = [head]
    if hundreds:
        parts.append(_HUNDREDS[hundreds])
    if tail == 0:
        return " ".join(parts[:-1] + [_ord_gen_from_hundreds(hundreds)]) if hundreds \
            else " ".join(parts)
    parts.append(_ord_gen(tail))
    return " ".join(p for p in parts if p)


def _ord_gen_from_hundreds(hundreds: int) -> str:
    return {1: "сотого", 2: "двухсотого", 3: "трёхсотого", 4: "четырёхсотого",
            5: "пятисотого", 6: "шестисотого", 7: "семисотого",
            8: "восьмисотого", 9: "девятисотого"}[hundreds]


def _ord_gen(value: int) -> str:
    """1–99 as a masculine genitive ordinal."""
    if value in _ORD_GEN_M:
        return _ORD_GEN_M[value]
    tens, ones = divmod(value, 10)
    if tens == 1:  # 11–19 are all in the table
        return _ORD_GEN_M[value]
    return f"{_TENS[tens]} {_ORD_GEN_M[ones]}".strip()


def date_to_words(value: date) -> str:
    """«Двадцать шестое июля две тысячи двадцать шестого года»."""
    text = (f"{day_to_words(value.day)} {_MONTHS_GEN[value.month]} "
            f"{_year_ordinal_genitive(value.year)} года")
    return text[0].upper() + text[1:]


# -- money -----------------------------------------------------------------

def amount_to_words(rubles: int, kopecks: int = 0, *, digits_kopecks: bool = True) -> str:
    """«Десять тысяч рублей 00 копеек».

    ``digits_kopecks`` keeps kopecks as two digits (the notarial habit); set it
    False to spell them out as well.
    """
    rub_words = number_to_words(rubles, feminine=False)
    rub_unit = plural(rubles, "рубль", "рубля", "рублей")
    kop_unit = plural(kopecks, "копейка", "копейки", "копеек")
    if digits_kopecks:
        kop = f"{kopecks:02d}"
    else:
        kop = number_to_words(kopecks, feminine=True) if kopecks else "ноль"
    text = f"{rub_words} {rub_unit} {kop} {kop_unit}"
    return text[0].upper() + text[1:]


def parse_amount(text: str) -> tuple[int, int]:
    """Read «10 000,00» / «10000.5» / «27500» → (rubles, kopecks).

    Raises ValueError when the text holds no usable number.
    """
    cleaned = (text or "").strip().replace(" ", " ").replace(" ", "")
    cleaned = cleaned.replace("₽", "").replace("руб.", "").replace("руб", "")
    cleaned = cleaned.replace(",", ".")
    if not cleaned:
        raise ValueError("empty amount")
    if cleaned.count(".") > 1:  # 1.234.567 → thousands separators
        head, _, tail = cleaned.rpartition(".")
        cleaned = head.replace(".", "") + "." + tail
    negative = cleaned.startswith("-")
    cleaned = cleaned.lstrip("+-")
    if not cleaned.replace(".", "").isdigit():
        raise ValueError(f"not a number: {text!r}")
    if "." in cleaned:
        whole, frac = cleaned.split(".")
        frac = (frac + "00")[:2]
    else:
        whole, frac = cleaned, "00"
    rubles = int(whole or 0)
    return (-rubles if negative else rubles), int(frac)


def format_amount(rubles: int, kopecks: int) -> str:
    """«10 000,00» — the digits form used on the documents."""
    return f"{rubles:,}".replace(",", " ") + f",{kopecks:02d}"
