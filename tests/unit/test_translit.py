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
