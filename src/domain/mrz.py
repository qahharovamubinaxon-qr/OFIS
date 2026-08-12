"""The two lines at the foot of a passport or a visa — ICAO 9303, TD3.

The office prints forms that carry a machine-readable zone of their own, and
typing one by hand is not a thing anyone can do: every line is exactly 44
characters, the names are padded with «<» to the letter, and five of the
characters are CHECK DIGITS worked out by weighted arithmetic over the ones
before them. One digit wrong and a scanner rejects the whole document.

So it is built here, from the worker's own data, and never typed.

    P<TJKISOEV<<ASLIDIN<<<<<<<<<<<<<<<<<<<<<<<<<
    4058472736TJK9907250M35011733500014207761<40

Line one says what the document is, who issued it and who it belongs to.
Line two carries the number, the nationality, the birth date, the sex, the
expiry and the personal number — each followed by its own check digit, and
the whole line closed by one more over all of them together.

What is NOT invented
--------------------
A field with nothing to put in it is filled with «<», which is what the
standard says an absent value looks like. Nothing is guessed: a missing
expiry date becomes «<<<<<<», not today plus ten years.
"""

from __future__ import annotations

from datetime import date

from src.domain.document_number import check_digit

#: Every line of a TD3 zone is exactly this long, padded with «<».
WIDTH = 44
LINES = 2
FILLER = "<"

#: ISO 3166-1 alpha-3 for the countries the office actually sees. A
#: citizenship it does not know is left blank rather than guessed — a wrong
#: country code makes the line's check digit wrong as well.
COUNTRIES: dict[str, str] = {
    "таджикистан": "TJK", "точикистон": "TJK", "tajikistan": "TJK",
    "узбекистан": "UZB", "ўзбекистон": "UZB", "uzbekistan": "UZB",
    "туркменистан": "TKM", "turkmenistan": "TKM",
    "киргизия": "KGZ", "кыргызстан": "KGZ", "kyrgyzstan": "KGZ",
    "казахстан": "KAZ", "kazakhstan": "KAZ",
    "россия": "RUS", "российская федерация": "RUS", "russia": "RUS",
    "азербайджан": "AZE", "армения": "ARM", "молдова": "MDA",
    "беларусь": "BLR", "украина": "UKR", "грузия": "GEO",
}

#: Cyrillic → the Latin ICAO 9303 sets a machine strip in. Used only when the
#: passport's own Latin spelling is not to hand; the printed one always wins,
#: because that is what the document itself is checked against.
_LATIN: dict[str, str] = {
    "а": "A", "б": "B", "в": "V", "г": "G", "д": "D", "е": "E", "ё": "E",
    "ж": "ZH", "з": "Z", "и": "I", "й": "I", "к": "K", "л": "L", "м": "M",
    "н": "N", "о": "O", "п": "P", "р": "R", "с": "S", "т": "T", "у": "U",
    "ф": "F", "х": "KH", "ц": "TS", "ч": "CH", "ш": "SH", "щ": "SHCH",
    "ъ": "", "ы": "Y", "ь": "", "э": "E", "ю": "IU", "я": "IA",
    "ғ": "G", "қ": "Q", "ҳ": "H", "ў": "O", "ҷ": "J", "ӣ": "I", "ӯ": "U",
}


def country_of(citizenship: str) -> str:
    """«Республика Таджикистан» → «TJK». Unknown → "" rather than a guess."""
    said = " ".join((citizenship or "").split()).lower()
    if not said:
        return ""
    if len(said) == 3 and said.isalpha() and said.isascii():
        return said.upper()
    for word, code in COUNTRIES.items():
        if word in said:
            return code
    return ""


def latin(text: str) -> str:
    """A name in the letters a machine strip is allowed to carry: A–Z only."""
    out = []
    for char in (text or ""):
        if char.isascii() and char.isalpha():
            out.append(char.upper())
        elif char.lower() in _LATIN:
            out.append(_LATIN[char.lower()])
        elif char in " -'ʻʼ‘’`":
            out.append(FILLER)
        # anything else — a digit, a stray mark — has no place in a name
    return "".join(out)


def _pad(text: str, width: int) -> str:
    """Exactly ``width`` characters: cut what is too long, fill what is short."""
    return (text or "")[:width].ljust(width, FILLER)


def _six(when: date | None) -> str:
    """YYMMDD, or «<<<<<<» when the date is not known."""
    return when.strftime("%y%m%d") if when else FILLER * 6


def name_line(surname: str, given: str, country: str,
              kind: str = "P") -> str:
    """Line one: what the document is, who issued it, whose it is."""
    head = _pad(f"{kind}{FILLER}{_pad(country, 3)}", 5)
    names = f"{latin(surname)}{FILLER}{FILLER}{latin(given)}"
    return _pad(head + names, WIDTH)


def data_line(number: str, nationality: str, born: date | None, sex: str,
              expires: date | None, personal: str = "") -> str:
    """Line two: the number, the person, the dates — each with its check digit.

    The last character checks all of them together, which is what a scanner
    uses to tell a misread from a forgery.
    """
    doc = _pad("".join((number or "").split()).upper(), 9)
    doc_check = check_digit(doc) or "0"
    birth = _six(born)
    birth_check = check_digit(birth) or "0"
    end = _six(expires)
    end_check = check_digit(end) or "0"
    person = _pad("".join((personal or "").split()).upper(), 14)
    person_check = check_digit(person) or "0"
    male = str(sex or "").strip().lower()
    letter = ("M" if male.startswith(("m", "м", "erk")) else
              "F" if male.startswith(("f", "ж", "ayo")) else FILLER)

    body = (f"{doc}{doc_check}{_pad(nationality, 3)}{birth}{birth_check}"
            f"{letter}{end}{end_check}{person}{person_check}")
    # the composite runs over the document, the dates and the personal
    # number — everything but the nationality and the sex
    composite = check_digit(doc + doc_check + birth + birth_check
                            + end + end_check + person + person_check) or "0"
    return _pad(body + composite, WIDTH)


def build(*, surname: str, name: str, citizenship: str, born: date | None,
          gender: str, number: str, expires: date | None = None,
          personal: str = "", kind: str = "P",
          surname_latin: str = "", name_latin: str = "") -> list[str]:
    """The whole zone, two lines of forty-four characters.

    The passport's OWN Latin spelling is used when it is to hand: that is
    what the document is checked against, and a transliteration of the
    Cyrillic can differ from it by a letter.
    """
    country = country_of(citizenship)
    return [
        name_line(surname_latin or surname, name_latin or name, country, kind),
        data_line(number, country, born, gender, expires, personal),
    ]


def as_text(lines: list[str]) -> str:
    return "\n".join(lines)


__all__ = ["COUNTRIES", "FILLER", "LINES", "WIDTH", "as_text", "build",
           "country_of", "data_line", "latin", "name_line"]
