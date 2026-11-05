"""Latin → Cyrillic transliteration, and Tajik Cyrillic → Russian Cyrillic."""

from __future__ import annotations

import pytest
from src.ocr.translit import to_cyrillic


def test_latin_names_to_cyrillic() -> None:
    assert to_cyrillic("KHUDAYBERDIEV") == "ХУДАЙБЕРДИЕВ"
    assert to_cyrillic("JASUR") == "ЖАСУР"
    assert to_cyrillic("UZBEKISTAN") == "УЗБЕКИСТАН"
    assert to_cyrillic("SHAROFIDDIN") == "ШАРОФИДДИН"


def test_already_cyrillic_unchanged() -> None:
    assert to_cyrillic("АЗИМОВ") == "АЗИМОВ"
    assert to_cyrillic("ТАДЖИКИСТАН") == "ТАДЖИКИСТАН"


def test_empty_and_digraphs() -> None:
    assert to_cyrillic("") == ""
    assert to_cyrillic("ZHASUR") == "ЖАСУР"
    assert to_cyrillic("CHORI") == "ЧОРИ"


@pytest.mark.parametrize("latin, russian", [
    # the endings every Uzbek passport carries — as the patents print them
    ("O'G'LI", "УГЛИ"), ("OʻGʻLI", "УГЛИ"), ("QIZI", "КИЗИ"),
    ("TESHA O'G'LI", "ТЕША УГЛИ"),
    # Ў is У in Russian, never О
    ("O'KTAM", "УКТАМ"), ("O'RALOV", "УРАЛОВ"), ("YO'LDOSHEV", "ЮЛДОШЕВ"),
    ("O'ZBEKISTON", "УЗБЕКИСТОН"),
    # a name may not OPEN with Е in Russian; inside a name Е stays
    ("ERGASH", "ЭРГАШ"), ("ELMURODOV", "ЭЛМУРОДОВ"), ("BEKZOD", "БЕКЗОД"),
    # the apostrophes come curly, straight and as the official okina
    ("G‘ANIYEV", "ГАНИЕВ"), ("G'ANIYEV", "ГАНИЕВ"),
])
def test_an_uzbek_passport_name_reads_like_its_patent(latin, russian) -> None:
    """The passport is Latin, the patent is Russian — they must be ONE name."""
    assert to_cyrillic(latin) == russian


@pytest.mark.parametrize("tajik, russian", [
    # the office's own rule: «Ҷ ҷ ҳарфлар русчасига Дж дж»
    ("ХОҶАЕВ", "ХОДЖАЕВ"), ("Хоҷаев", "Ходжаев"),
    ("ҶУМЪАЕВ", "ДЖУМЪАЕВ"), ("Ҷамшед", "Джамшед"),
    ("Ҷ", "ДЖ"), ("ҷ", "дж"),
    ("ТОҶИКИСТОН", "ТОДЖИКИСТОН"),
    # and the rest of the letters Russian has not
    ("ҒАФУРОВ", "ГАФУРОВ"), ("ҚӮРҒОНТЕППА", "КУРГОНТЕППА"),
    ("Шӯъбаи Ҳисор", "Шуъбаи Хисор"), ("ЛӢВОБОД", "ЛИВОБОД"),
])
def test_a_tajik_letter_never_reaches_a_russian_form(tajik, russian) -> None:
    """Reading a Tajik passport is not enough — it must be spelled in Russian."""
    assert to_cyrillic(tajik) == russian


@pytest.mark.parametrize("printed, country, russian", [
    # ---- Тоҷикистон: Ҷ is ДЖ in Cyrillic and J is ДЖ in Latin
    ("Ҷамшед", None, "Джамшед"), ("ХОҶАЕВ", None, "ХОДЖАЕВ"),
    ("JAMSHED", "ТАДЖИКИСТАН", "ДЖАМШЕД"),
    ("JURAEV", "ТАДЖИКИСТАН", "ДЖУРАЕВ"),
    ("SAFAROV", "ТАДЖИКИСТАН", "САФАРОВ"),
    # ---- Ўзбекистон: the same J is Ж
    ("JASUR", "УЗБЕКИСТАН", "ЖАСУР"), ("JAMSHID", "УЗБЕКИСТАН", "ЖАМШИД"),
    # ---- Кыргызстан
    ("Өмүрбек", None, "Омурбек"), ("Жеңиш", None, "Жениш"),
    # ---- Қазақстан
    ("Әбдіғаппар", None, "Абдигаппар"), ("Ұлан", None, "Улан"),
    ("Һасан", None, "Хасан"),
    # ---- Azərbaycan: C is ДЖ, Ə is А, and the old Cyrillic Ҹ is ДЖ too
    ("Cəfər", "АЗЕРБАЙДЖАН", "ДЖАФАР"), ("Əliyev", "АЗЕРБАЙДЖАН", "АЛИЕВ"),
    ("Ҹаваншир", None, "Джаваншир"),
    # ---- Türkmenistan: y after a consonant is ы
    ("Myrat", "ТУРКМЕНИСТАН", "МЫРАТ"),
    ("Ýazmyrat", "ТУРКМЕНИСТАН", "ЯЗМЫРАТ"),
    ("Şöhrat", "ТУРКМЕНИСТАН", "ШОХРАТ"),
    # ---- Moldova · Беларусь · Україна
    ("Ștefan", None, "ШТЕФАН"), ("Ўладзімір", None, "Уладзимир"),
    ("Їжакевич", None, "Ижакевич"),
])
def test_every_republic_s_letters_reach_a_russian_form(
        printed, country, russian) -> None:
    """The office's workers are not only Uzbek — every alphabet they carry."""
    assert to_cyrillic(printed, country) == russian


def test_the_citizenship_decides_the_one_letter_that_differs() -> None:
    """J is the only letter that depends on the republic — and it does."""
    assert to_cyrillic("JAMSHED", "ТАДЖИКИСТАН") != to_cyrillic(
        "JAMSHED", "УЗБЕКИСТАН")
    # everything else is the same wherever the passport is from
    for name in ("SHUKUROV", "KHOLMATOV", "O'G'LI", "ERGASH"):
        assert to_cyrillic(name, "ТАДЖИКИСТАН") == \
            to_cyrillic(name, "УЗБЕКИСТАН")
    # and an unknown citizenship never breaks anything
    assert to_cyrillic("SHUKUROV") == "ШУКУРОВ"


def test_the_rule_holds_wherever_a_name_comes_from() -> None:
    """Read, taken from the machine-readable zone, or typed by hand."""
    from src.domain.documents import MigrationCard, Passport, Patent, Registration

    passport = Passport(surname="Хоҷаев", name="Ҷамшед",
                        patronymic="Ҷумъаевич", nationality="ТОҶИКИСТОН",
                        birth_place="ҚӮРҒОНТЕППА", number="402543058")
    assert (passport.surname, passport.name, passport.patronymic) == \
        ("Ходжаев", "Джамшед", "Джумъаевич")
    assert passport.nationality == "ТОДЖИКИСТОН"
    assert passport.birth_place == "КУРГОНТЕППА"

    patent = Patent(number="1", profession="Ҷӯшкор", holder_surname="Хоҷаев",
                    holder_citizenship="ТОҶИКИСТОН")
    assert patent.profession == "Джушкор" and patent.holder_surname == "Ходжаев"

    assert Registration(address="ш. Хуҷанд, кӯчаи Ғафуров").address == \
        "ш. Худжанд, кучаи Гафуров"
    assert MigrationCard(purpose="Ҷустуҷӯи кор").purpose == "Джустуджуи кор"


def test_the_issuing_office_keeps_its_own_rule() -> None:
    """«ҶТ» is the republic, not letters to spell out — its rule runs first."""
    from src.domain.documents import Passport

    passport = Passport(surname="Хоҷаев", name="Ҷамшед", number="402543058",
                        nationality="ТАДЖИКИСТАН", issued_by="ХШБ ВКД ҶТ")
    assert passport.issued_by == "МВД РТ"
    assert passport.surname == "Ходжаев"


# --------------------------------------------------- Y after a consonant is ы
# The office found this on a registration it had already filed: «KYZY» had
# gone onto the paper as «КЙЗЙ». The rule existed but was applied to Turkmen
# passports only, so a Kyrgyz woman's patronymic missed it.
@pytest.mark.parametrize(("latin", "russian"), [
    ("KYZY", "КЫЗЫ"),            # «daughter of» — every republic prints it
    ("OGLY", "ОГЛЫ"),            # and its «son of»
    ("MYRAT", "МЫРАТ"),
    ("SADYKOV", "САДЫКОВ"),
    ("SYMBAT", "СЫМБАТ"),
    ("KYRGYZ", "КЫРГЫЗ"),
    ("NURYYEVA", "НУРЫЕВА"),
])
def test_a_y_standing_after_a_consonant_is_the_vowel(latin, russian) -> None:
    assert to_cyrillic(latin) == russian


@pytest.mark.parametrize("country", ["", "КИРГИЗИЯ", "ТУРКМЕНИСТАН",
                                     "КАЗАХСТАН", "УЗБЕКИСТАН"])
def test_it_is_the_same_for_every_republic(country) -> None:
    """It used to depend on the citizenship, and that was the bug."""
    assert to_cyrillic("GULNARA KYZY", country) == "ГУЛНАРА КЫЗЫ"


@pytest.mark.parametrize(("latin", "russian"), [
    ("KHUDAYBERDIEV", "ХУДАЙБЕРДИЕВ"),   # after a VOWEL it is still й
    ("BAYRAM", "БАЙРАМ"),
    ("SEYITOV", "СЕЙИТОВ"),
    ("DMITRIY", "ДМИТРИЙ"),
    ("AYGUL", "АЙГУЛ"),
    ("YUSUF", "ЮСУФ"),                   # …and the digraphs still win
    ("YAKUBOV", "ЯКУБОВ"),
    ("ILYAS", "ИЛЯС"),
    ("NIYAZOV", "НИЯЗОВ"),
    ("TYAN", "ТЯН"),
])
def test_a_y_after_a_vowel_or_in_a_digraph_is_untouched(latin,
                                                        russian) -> None:
    """Russian never puts й after a consonant, which is what makes the plain
    rule safe — but it very much puts it after a vowel."""
    assert to_cyrillic(latin) == russian


# ------------------------------------------------- Turkmen: J is the affricate
@pytest.mark.parametrize(("latin", "russian"), [
    ("JEREN", "ДЖЕРЕН"),
    ("OGULJAN", "ОГУЛДЖАН"),
    ("GYLYJOW", "ГЫЛЫДЖОВ"),
    ("HOJAMYRAT", "ХОДЖАМЫРАТ"),
])
def test_turkmen_j_is_dzh(latin, russian) -> None:
    """Turkmen Latin J is Cyrillic Җ, the /dʒ/ affricate — ДЖ, like Tajik."""
    assert to_cyrillic(latin, "Туркменистан") == russian


@pytest.mark.parametrize(("latin", "russian"), [
    ("ŽANNA", "ЖАННА"),           # Ž is the fricative — stays Ж
    ("MYRAT", "МЫРАТ"),           # Y after a consonant is Ы
    ("NADYYR", "НАДЫЙР"),         # …and the office's own example
    ("HALYL", "ХАЛЫЛ"),           # H is Х, not KH
    ("MAHMYT", "МАХМЫТ"),
])
def test_turkmen_the_rest_is_unchanged(latin, russian) -> None:
    """The office confirmed these already worked; the J fix must not touch them."""
    assert to_cyrillic(latin, "Туркменистан") == russian


# --------------------------------------------------- Turkey: C is the affricate
@pytest.mark.parametrize(("latin", "russian"), [
    ("CENGIZ", "ДЖЕНГИЗ"),
    ("CEMAL", "ДЖЕМАЛ"),
    ("ÇELIK", "ЧЕЛИК"),           # Ç stays Ч
    ("MURATOV", "МУРАТОВ"),
])
def test_turkish_c_is_dzh(latin, russian) -> None:
    assert to_cyrillic(latin, "Турция") == russian


def test_turkey_never_catches_turkmenistan() -> None:
    """«TUR» is a prefix of both — the Turkish rule must not fire on a Turkmen
    passport, or Turkmen J would wrongly become Ж again through the C branch."""
    assert to_cyrillic("OGULJAN", "TURKMENISTAN") == "ОГУЛДЖАН"
    assert to_cyrillic("CENGIZ", "TURKEY") == "ДЖЕНГИЗ"


# --------------------------------------------------- Spanish: Cuba, Philippines
@pytest.mark.parametrize(("latin", "russian"), [
    ("JOSE", "ХОСЕ"),                     # J → Х
    ("JULIO", "ХУЛИО"),
    ("JIMENEZ", "ХИМЕНЕС"),               # J → Х, Z → С
    ("GONZALEZ", "ГОНСАЛЕС"),             # Z → С
    ("HERNANDEZ", "ЭРНАНДЕС"),            # silent H, opening E → Э
    ("ANGEL", "АНХЕЛЬ"),                  # G before e → Х, final l → ль
    ("GIL", "ХИЛЬ"),
    ("CARLOS", "КАРЛОС"),                 # C before a → К
    ("CECILIA", "СЕСИЛИЯ"),               # C before e → С, final -ia → -ия
    ("ENRIQUE", "ЭНРИКЕ"),                # qu → к, u silent
    ("MIGUEL", "МИГЕЛЬ"),                 # gu → г, final l → ль
    ("RAFAEL", "РАФАЭЛЬ"),                # E after a vowel → Э
])
def test_spanish_cuba(latin, russian) -> None:
    assert to_cyrillic(latin, "Куба") == russian


def test_spanish_philippines() -> None:
    assert to_cyrillic("JOSE MAGSAYSAY", "Филиппины") == "ХОСЕ МАГСАЙСАЙ"


# ----------------------------------------------------------- India: English J
@pytest.mark.parametrize(("latin", "russian"), [
    ("RAJ", "РАДЖ"),
    ("RAJESH", "РАДЖЕШ"),
    ("SINGH", "СИНГ"),            # a final -gh is silent-h: СИНГ, not СИНГХ
])
def test_india_english(latin, russian) -> None:
    assert to_cyrillic(latin, "Индия") == russian


# ------------------------------------------- Central Asia is left exactly as-is
@pytest.mark.parametrize(("latin", "country", "russian"), [
    ("JASUR", "Ўзбекистон", "ЖАСУР"),          # Uzbek J stays Ж
    ("JAMSHED", "Таджикистан", "ДЖАМШЕД"),      # Tajik J stays ДЖ
    ("KYZY", "Кыргызстан", "КЫЗЫ"),
    ("SADYKOV", "Казахстан", "САДЫКОВ"),
    ("CEYHUN", "Азербайджан", "ДЖЕЙХУН"),       # Azeri C stays ДЖ
])
def test_the_republics_are_untouched(latin, country, russian) -> None:
    assert to_cyrillic(latin, country) == russian


# --------------------------------------------------- серия/рақам таржима эмас
# «СЕРИЯ РАКАМЛАР ПЕРЕВОД БОЛМАЙДИ, КАНДАЙ БОЛСА ШУНДАЙ ЙОЗИЛАДИ» — ичида
# рақами бор ҳар сўз белги: уни ўгириш ҳужжатни яроқсиз қилади.
@pytest.mark.parametrize("printed", [
    "FB2254876",                 # паспорт серияси + рақами
    "AA1234567",
    "XW8ZZZ61ZJG011111",         # ВИН
    "T566BE40",                  # лотинча терилган давлат рақами
    "Т566ВЕ40",                  # кириллча терилгани — у ҳам ўзгармайди
    "50 ОЕ 202246",
    "77AB123456",
])
def test_an_identifier_is_copied_as_printed(printed) -> None:
    assert to_cyrillic(printed) == printed


def test_a_name_beside_a_number_still_becomes_russian() -> None:
    """Рақам тегилмайди, ёнидаги сўз эса одатдагидек ўгирилади."""
    assert to_cyrillic("JASUR FB2254876") == "ЖАСУР FB2254876"
    assert to_cyrillic("MVD 22220") == "МВД 22220"


def test_a_plain_name_is_not_affected_by_the_rule() -> None:
    assert to_cyrillic("KHUDAYBERDIEV") == "ХУДАЙБЕРДИЕВ"
    assert to_cyrillic("JASUR UGLI") == "ЖАСУР УГЛИ"


def test_as_printed_only_tidies_the_spaces() -> None:
    from src.ocr.translit import as_printed

    assert as_printed("  T566BE40 ") == "T566BE40"
    assert as_printed("50  ОЕ   202246") == "50 ОЕ 202246"
    assert as_printed(None) == ""


# Қоида ТОР бўлиши шарт: манзилдаги «D.33», «19-MAVZE» белги эмас — улар
# нуқта/тире билан ёзилади ва русчага ўгирилиши керак. Акс ҳолда манзил ярим
# лотин бўлиб қолади.
#
# Эслатма: бу ерда фақат ҲАРФ қатлами синалади. Сўзнинг ўзини таржима қилиш
# (УЙ → ДОМ) — :func:`address_in_russian` нинг иши, у қуйида синалади.
@pytest.mark.parametrize("latin, russian", [
    ("UL. LENINA, D. 5, KV. 12", "УЛ. ЛЕНИНА, Д. 5, КВ. 12"),
    ("D.33 KORP.2 KV.15", "Д.33 КОРП.2 КВ.15"),
    ("19-MAVZE, 4-UY", "19-МАВЗЕ, 4-УЙ"),
    ("1-SON", "1-СОН"),
])
def test_an_address_with_numbers_still_becomes_russian(latin, russian) -> None:
    assert to_cyrillic(latin) == russian


@pytest.mark.parametrize("token, identifier", [
    ("FB2254876", True), ("T566BE40", True), ("77AB123456", True),
    ("XW8ZZZ61ZJG011111", True), ("Т566ВЕ40", True),
    ("D.33", False), ("19-MAVZE", False), ("KV.15", False),
    ("4-UY", False), ("D5", False),          # жуда қисқа — манзил бўлаги
    ("LENINA", False), ("12", False),
])
def test_what_counts_as_an_identifier(token, identifier) -> None:
    from src.ocr.translit import is_identifier

    assert is_identifier(token) is identifier


def test_an_identifier_in_brackets_is_still_left_alone() -> None:
    assert to_cyrillic("(FB2254876)") == "(FB2254876)"
    assert to_cyrillic("VIN: XW8ZZZ61ZJG011111") == "ВИН: XW8ZZZ61ZJG011111"


# ------------------------------------------------- манзил сўзлари таржимаси
# Офис: «уй бу дом, хонадон квартира, куча улица» — ҳарфма-ҳарф ўгириш эмас,
# ТАРЖИМА, ва рус тартибида (от номдан олдин).
def _address(text: str) -> str:
    from src.domain.passport_rules import address_in_russian

    return address_in_russian(to_cyrillic(text))


@pytest.mark.parametrize("uzbek, russian", [
    ("4-UY", "ДОМ 4"),
    ("19-MAVZE", "МАССИВ 19"),
    ("12-XONADON", "КВАРТИРА 12"),
    ("TOSHKENT SHAHRI", "ГОРОД ТОШКЕНТ"),
    ("YUNUSOBOD TUMANI", "РАЙОН ЮНУСОБОД"),
    ("SURXONDARYO VILOYATI", "ОБЛАСТЬ СУРХОНДАРЁ"),
    ("GULISTON QISHLOG'I", "СЕЛО ГУЛИСТОН"),
    ("NAVOIY KO'CHASI", "УЛИЦА НАВОИЙ"),
    ("CHILONZOR MAHALLASI", "МАХАЛЛЯ ЧИЛОНЗОР"),
    # кўп сўзли ном бутунлигича кўчади
    ("AMIR TEMUR XIYOBONI", "ПРОСПЕКТ АМИР ТЕМУР"),
])
def test_an_address_word_is_translated_not_transliterated(uzbek, russian):
    assert _address(uzbek) == russian


def test_a_number_never_becomes_the_name() -> None:
    """«19-массив 4-уй» — вергулсиз ёзилса ҳам «дом 19-массив» чиқмайди."""
    assert _address("19-MAVZE 4-UY") == "МАССИВ 19 ДОМ 4"


def test_a_whole_uzbek_address_reads_as_a_russian_one() -> None:
    assert _address("TOSHKENT SHAHRI, YUNUSOBOD TUMANI, 19-MAVZE, 4-UY, "
                    "12-XONADON") == (
        "ГОРОД ТОШКЕНТ, РАЙОН ЮНУСОБОД, МАССИВ 19, ДОМ 4, КВАРТИРА 12")


@pytest.mark.parametrize("tajik, russian", [
    ("NOHIYAI RUDAKI", "РАЙОН РУДАКИ"),
    ("DEHAI CHORTEPPA", "СЕЛО ЧОРТЕППА"),
    ("KUCHAI LENIN", "УЛИЦА ЛЕНИН"),
])
def test_a_tajik_address_keeps_its_order(tajik, russian) -> None:
    """Тожикчада от аллақачон олдинда — ўрин алмаштирилмайди."""
    assert _address(tajik) == russian


@pytest.mark.parametrize("russian", [
    "Г. МОСКВА, УЛ. ЛЕНИНА, Д. 5, КВ. 12",
    "МОСКОВСКАЯ ОБЛАСТЬ, Г. БАЛАШИХА, УЛ. МИРА, Д. 33, КОРП. 2",
])
def test_a_russian_address_is_left_exactly_as_it_is(russian) -> None:
    assert _address(russian) == russian


def test_a_place_name_is_never_translated() -> None:
    """Фақат турдош от таржима қилинади — ном эмас."""
    assert "ЮНУСОБОД" in _address("YUNUSOBOD TUMANI")
    assert "НАВОИЙ" in _address("NAVOIY KO'CHASI")
