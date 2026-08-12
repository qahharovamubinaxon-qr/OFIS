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

# Longest sequences first so digraphs win over single letters. These are
# the practical-transcription rules a Russian form uses for Uzbek Latin:
# the same ones the patents print the worker's name by, so the passport
# and the patent come out as ONE name.
_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("SHCH", "Щ"), ("SCH", "Щ"),
    ("YO'", "Ю"),                 # YO'LDOSHEV → ЮЛДОШЕВ, the patents' way
    ("KH", "Х"), ("ZH", "Ж"), ("CH", "Ч"), ("SH", "Ш"), ("TS", "Ц"),
    ("YO", "Ё"), ("YU", "Ю"), ("YA", "Я"), ("YE", "Е"),
    # Uzbek Oʻ is the Cyrillic Ў, and Russian writes Ў as У: OʻG'LI is
    # УГЛИ (never ОГЛИ), OʻKTAM is УКТАМ, OʻZBEKISTON is УЗБЕКИСТОН
    ("O'", "У"), ("G'", "Г"),
)

_SINGLE: dict[str, str] = {
    "A": "А", "B": "Б", "C": "К", "D": "Д", "E": "Е", "F": "Ф", "G": "Г",
    "H": "Х", "I": "И", "J": "Ж", "K": "К", "L": "Л", "M": "М", "N": "Н",
    "O": "О", "P": "П", "Q": "К", "R": "Р", "S": "С", "T": "Т", "U": "У",
    "V": "В", "W": "В", "X": "Х", "Y": "Й", "Z": "З", "'": "", "`": "",
}

#: The OTHER republics' Latin alphabets, folded to their plain letters
#: before the table above runs. Azerbaijani (Ə Ğ Ş Ç Ö Ü İ), Turkmen
#: (Ä Ž Ň Ý Ş Ö Ü), Moldovan (Ă Â Î Ș Ț) and the accents a scanner may
#: leave on any of them — «Əliyev» is Алиев, «Şöhrat» is Шохрат,
#: «Ștefan» is Штефан.
_LATIN_FOLD = str.maketrans({
    "Ə": "A", "Ä": "A", "Ă": "A", "Â": "A", "À": "A", "Á": "A",
    "Ğ": "G", "Ģ": "G",
    "Ş": "SH", "Ș": "SH", "Š": "SH",
    "Ç": "CH", "Č": "CH", "Ć": "CH",
    "Ž": "ZH", "Ź": "ZH", "Ż": "ZH",
    "Ö": "O", "Ó": "O", "Ô": "O", "Ő": "O", "Ø": "O",
    "Ü": "U", "Ú": "U", "Ù": "U", "Ű": "U", "Ū": "U", "Ų": "U",
    "İ": "I", "Í": "I", "Î": "I", "Ï": "I", "Ī": "I", "Į": "I",
    "Ň": "N", "Ń": "N", "Ñ": "N", "Ņ": "N",
    "Ý": "Y", "Ÿ": "Y",
    "Ţ": "TS", "Ț": "TS",
    "Ė": "E", "É": "E", "È": "E", "Ê": "E", "Ë": "E", "Ě": "E",
    "Ł": "L", "Ļ": "L", "Ř": "R", "Ķ": "K", "Ď": "D", "Ť": "T",
    "Ğ".lower(): "G", "ß": "SS", "Æ": "A", "Œ": "O",
})

#: Where «J» is «ДЖ» and not «Ж»: a Tajik Jamshed is ДЖАМШЕД (his own
#: passport prints Ҷамшед) where an Uzbek Jasur is ЖАСУР.
_J_IS_DZH = ("ТАДЖИКИСТАН", "ТОДЖИКИСТОН", "ТОЧИКИСТОН", "TAJIKISTAN",
             "TJK", "ТЖК")
#: Azerbaijani spells that same sound with C — Cəfər is ДЖАФАР — and its
#: J is Ж (Jale is ЖАЛЯ).
_AZERI = ("АЗЕРБАЙДЖАН", "AZERBAIJAN", "AZE", "ОЗАРБАЙЖОН")

def _is(country: str, names: tuple[str, ...]) -> bool:
    return any(name in country for name in names)

#: Every apostrophe an Uzbek document may carry — the official okina ʻ,
#: the typewriter ', the curly pair, the modifier ʼ — folded to one, so
#: OʻGʻLI and O'G'LI read the same.
_APOSTROPHES = str.maketrans({c: "'" for c in "ʻʼ‘’′`´"})


def _has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= c <= "ӿ" for c in text)


def to_cyrillic(text: str, country: str | None = None) -> str:
    """Latin → Cyrillic, and Cyrillic → RUSSIAN Cyrillic.

    ``country`` is the holder's citizenship when it is known — the one
    letter that depends on it is J: an Uzbek Jasur is ЖАСУР, a Tajik
    Jamshed is ДЖАМШЕД. Everything else is the same for every republic.
    Empty text is unchanged.
    """
    if not text:
        return text
    if _has_cyrillic(text):
        return in_russian_letters(text)
    t = text.upper().translate(_APOSTROPHES).translate(_LATIN_FOLD)
    upper = (country or "").upper()
    j_is_dzh = _is(upper, _J_IS_DZH)
    azeri = _is(upper, _AZERI)
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
        char = t[i]
        before = t[i - 1] if i else ""
        if char == "E" and (i == 0 or not before.isalpha()):
            # a Russian word never OPENS with Е for this sound: ERGASH is
            # ЭРГАШ, ELMUROD is ЭЛМУРОД (mid-word E stays Е: БЕК, СЕРГЕЙ)
            out.append("Э")
        elif (char == "J" and j_is_dzh) or (char == "C" and azeri):
            # the same sound, spelled J by Tajikistan and C by Azerbaijan
            out.append("ДЖ")
        elif char == "Y" and before and before not in "AEIOUY":
            # A Y standing after a CONSONANT is the vowel ы, not the
            # semivowel й — and this is not one republic's habit but how the
            # whole practical transcription works:
            #
            #   KYZY  → КЫЗЫ    the «daughter of» every republic prints
            #   OGLY  → ОГЛЫ    and its «son of»
            #   MYRAT → МЫРАТ · SADYKOV → САДЫКОВ · SYMBAT → СЫМБАТ
            #
            # It used to be applied to Turkmen passports only, so a Kyrgyz
            # woman's patronymic went onto a registration as «КЙЗЙ». Russian
            # does not put й after a consonant at all, which is why the plain
            # rule is safe: after a VOWEL it is still й (БАЙРАМ, ХУДАЙБЕРДИЕВ,
            # ДМИТРИЙ), and YA/YE/YO/YU are taken by the digraphs above.
            out.append("Ы")
        else:
            out.append(_SINGLE.get(char, char))
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
