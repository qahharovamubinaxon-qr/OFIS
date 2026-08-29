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

#: Countries whose Latin «J» is the affricate ДЖ, not the fricative Ж.
#:
#: *Tajikistan* — a Tajik Jamshed is ДЖАМШЕД (his own passport prints Ҷамшед),
#: where an Uzbek Jasur is ЖАСУР.
#: *Turkmenistan* — Turkmen has TWO letters here: J is the affricate (Cyrillic
#: Җ → ДЖ) and Ž is the fricative (Cyrillic Ж → Ж). So Oguljan is ОГУЛДЖАН and
#: Jeren is ДЖЕРЕН, while Žanna stays ЖАННА. Confirmed against the Turkmen
#: Latin↔Cyrillic table.
#: *India* — English J is /dʒ/: Raj is РАДЖ, Rajesh РАДЖЕШ.
_TAJIK_C = ("ТАДЖИКИСТАН", "ТОДЖИКИСТОН", "ТОЧИКИСТОН", "TAJIKISTAN",
            "TJK", "ТЖК")
_TURKMEN = ("ТУРКМЕН", "ТУРКМАН", "TURKMEN", "TKM")
_INDIA = ("ИНДИЯ", "ХИНДИСТОН", "ҲИНДИСТОН", "INDIA")
_J_IS_DZH = _TAJIK_C + _TURKMEN + _INDIA

#: Countries whose Latin «C» is ДЖ. Azerbaijani Cəfər is ДЖАФАР; Turkish Cengiz
#: is ДЖЕНГИЗ. Both spell the /dʒ/ sound with C, and their J stays Ж.
#: Turkey is kept clear of «TUR» so it never catches Turkmenistan.
_AZERI = ("АЗЕРБАЙДЖАН", "AZERBAIJAN", "AZE", "ОЗАРБАЙЖОН")
_TURKEY = ("ТУРЦИЯ", "ТУРКИЯ", "TURKEY", "TURKIYE", "TÜRKIYE", "TÜRKİYE")
_C_IS_DZH = _AZERI + _TURKEY

#: Spanish-speaking passports: Cuba, and the Spanish-named Philippines. Their
#: letters follow the Spanish sound system, which is a different table — see
#: :func:`_spanish`. José is ХОСЕ, not ЖОСЕ; González is ГОНСАЛЕС.
_SPANISH = ("КУБА", "CUBA", "ФИЛИППИН", "PHILIPPINES", "PILIPINAS", "PHL")


def _is(country: str, names: tuple[str, ...]) -> bool:
    return any(name in country for name in names)


#: The vowels that soften a Spanish C and G into С and Х.
_ES_SOFT = "EI"
_ES_VOWEL = "AEIOU"
_RU_VOWELS = "АЕЁИОУЫЭЮЯ"


def _es_opening(t: str, i: int) -> bool:
    """Is the letter at ``i`` the first sound of its word?

    True at a word boundary — and also right after a word-initial silent H,
    because Spanish does not pronounce it: «Hernández» opens on the E, so the
    E is Э, giving ЭРНАНДЕС.
    """
    if i == 0 or not t[i - 1].isalpha():
        return True
    return t[i - 1] == "H" and (i - 1 == 0 or not t[i - 2].isalpha())


def _spanish(t: str) -> str:
    """Spanish spelling → Russian, for a Cuban or Filipino name.

    Only the letters that carry a different sound in Spanish:
    J and G-before-e/i are Х (José ХОСЕ, Ángel АНХЕЛЬ); C is С before e/i and
    К otherwise (Cecilia СЕСИЛИЯ, Carlos КАРЛОС); Z is С (González ГОНСАЛЕС);
    H is silent (Hernández ЭРНАНДЕС) but CH stays Ч; LL is ЛЬ; a word-opening
    E is Э; a final -l softens to -ль (Miguel МИГЕЛЬ); a final -ia is -ия
    (María МАРИЯ). QU/GU before e/i drop the U. Everything else falls through
    the ordinary single-letter table.
    """
    out: list[str] = []
    i, n = 0, len(t)
    while i < n:
        two = t[i:i + 2]
        after2 = t[i + 2] if i + 2 < n else ""
        ch = t[i]
        nxt = t[i + 1] if i + 1 < n else ""
        word_end2 = i + 2 >= n or not t[i + 2].isalpha()
        if two == "CH":
            out.append("Ч")
            i += 2
        elif two == "LL":
            out.append("ЛЬ")
            i += 2
        elif two == "QU" and after2 in _ES_SOFT:
            out.append("К")               # que/qui — the u is silent
            i += 2
        elif two == "GU" and after2 in _ES_SOFT:
            out.append("Г")               # gue/gui — the u is silent
            i += 2
        elif ch == "I" and nxt == "A" and word_end2:
            out.append("ИЯ")              # final -ía/-ia: María МАРИЯ
            i += 2
        elif ch == "C":
            out.append("С" if nxt in _ES_SOFT else "К")
            i += 1
        elif ch == "G":
            out.append("Х" if nxt in _ES_SOFT else "Г")
            i += 1
        elif ch == "J":
            out.append("Х")
            i += 1
        elif ch == "Z":
            out.append("С")
            i += 1
        elif ch == "H":
            i += 1                        # silent (CH already taken above)
        elif ch == "E" and (_es_opening(t, i)
                            or (out and out[-1][-1] in _RU_VOWELS)):
            # Э at a word opening and after a vowel: Enrique ЭНРИКЕ, Rafael
            # РАФАЭЛЬ — but Е after a consonant: José ХОСЕ. The previous
            # OUTPUT letter is what decides, so a silent gu/qu-u (already
            # gone) never counts as the vowel before.
            out.append("Э")
            i += 1
        elif ch == "L" and (not nxt or nxt not in _ES_VOWEL):
            out.append("ЛЬ")             # final/pre-consonant l: Miguel МИГЕЛЬ
            i += 1
        elif ch == "Y":
            before = t[i - 1] if i else ""
            out.append("Й" if before in _ES_VOWEL else "И")
            i += 1
        else:
            out.append(_SINGLE.get(ch, ch))
            i += 1
    return "".join(out)

#: Every apostrophe an Uzbek document may carry — the official okina ʻ,
#: the typewriter ', the curly pair, the modifier ʼ — folded to one, so
#: OʻGʻLI and O'G'LI read the same.
_APOSTROPHES = str.maketrans({c: "'" for c in "ʻʼ‘’′`´"})


def _has_cyrillic(text: str) -> bool:
    return any("Ѐ" <= c <= "ӿ" for c in text)


def to_cyrillic(text: str, country: str | None = None) -> str:
    """Latin → Cyrillic, and Cyrillic → RUSSIAN Cyrillic.

    ``country`` is the holder's citizenship when it is known — several
    letters depend on it. An Uzbek Jasur is ЖАСУР but a Tajik or Turkmen
    Jamshed is ДЖАМШЕД; a Turkish Cengiz is ДЖЕНГИЗ; a Cuban José is ХОСЕ.
    With no country the plain Central-Asian table is used. Empty text is
    unchanged.
    """
    if not text:
        return text
    if _has_cyrillic(text):
        return in_russian_letters(text)
    t = text.upper().translate(_APOSTROPHES).translate(_LATIN_FOLD)
    upper = (country or "").upper()
    if _is(upper, _SPANISH):
        # a wholly different sound system — its own pass, not the table below
        return in_russian_letters(_spanish(t))
    j_is_dzh = _is(upper, _J_IS_DZH)
    c_is_dzh = _is(upper, _C_IS_DZH)
    india = _is(upper, _INDIA)
    out: list[str] = []
    i = 0
    n = len(t)
    while i < n:
        if india and t.startswith("GH", i) and (
                i + 2 >= n or not t[i + 2].isalpha()):
            # an Indian «-gh» at the end of a name is silent-h: Singh is СИНГ,
            # not СИНГХ. Word-internal gh (before a vowel) is left alone.
            out.append("Г")
            i += 2
            continue
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
        elif (char == "J" and j_is_dzh) or (char == "C" and c_is_dzh):
            # the same /dʒ/ sound: spelled J by Tajikistan, Turkmenistan and
            # India; spelled C by Azerbaijan and Turkey
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
