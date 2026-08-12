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
