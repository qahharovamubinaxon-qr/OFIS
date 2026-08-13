"""The two lines at the foot of a passport or a visa — ICAO 9303, TD3.

Every line is exactly 44 characters and five of them are check digits worked
out by weighted arithmetic. One digit wrong and a scanner rejects the whole
document, so the first thing checked here is the standard's OWN published
example, character for character. If that passes, the arithmetic is right.
"""

from __future__ import annotations

from datetime import date

import pytest
from src.domain import mrz
from src.domain.document_number import check_digit

#: ICAO 9303 part 4, the specimen zone. If this fails, nothing else matters.
ICAO_LINE_1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
ICAO_LINE_2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def test_the_standards_own_example_comes_out_character_for_character() -> None:
    assert mrz.name_line("ERIKSSON", "ANNA MARIA", "UTO") == ICAO_LINE_1
    assert mrz.data_line("L898902C3", "UTO", date(1974, 8, 12), "F",
                         date(2012, 4, 15), "ZE184226B") == ICAO_LINE_2


def test_every_line_is_exactly_forty_four_characters() -> None:
    lines = mrz.build(surname="Исоев", name="Аслидин",
                      citizenship="Республика Таджикистан",
                      born=date(1999, 7, 25), gender="Мужской",
                      number="405847273", expires=date(2035, 1, 17))
    assert len(lines) == mrz.LINES == 2
    assert all(len(line) == mrz.WIDTH == 44 for line in lines)


# --------------------------------------------------------- the check digits
def test_each_check_digit_checks_what_it_should() -> None:
    """Pull the line apart and re-do the arithmetic on each piece."""
    line = mrz.data_line("405847273", "TJK", date(1999, 7, 25), "M",
                         date(2035, 1, 17), "50707994120019")
    assert line[9] == check_digit(line[0:9]), "ҳужжат рақами"
    assert line[19] == check_digit(line[13:19]), "туғилган сана"
    assert line[27] == check_digit(line[21:27]), "амал қилиш охири"
    assert line[42] == check_digit(line[28:42]), "шахсий рақам"
    composite = line[0:10] + line[13:20] + line[21:43]
    assert line[43] == check_digit(composite), "умумий назорат рақами"


def test_a_scanner_would_reject_a_single_altered_digit() -> None:
    """What the check digits are FOR — proving they actually catch a change."""
    line = mrz.data_line("405847273", "TJK", date(1999, 7, 25), "M",
                         date(2035, 1, 17))
    broken = line[:3] + ("9" if line[3] != "9" else "8") + line[4:]
    assert broken[9] != check_digit(broken[0:9])


# ---------------------------------------------------------------- the names
def test_a_cyrillic_name_is_set_in_the_latin_a_strip_allows() -> None:
    assert mrz.latin("Исоев") == "ISOEV"
    assert mrz.latin("Жўраев") == "ZHORAEV"
    assert mrz.latin("Хамидов") == "KHAMIDOV"
    assert mrz.latin("Шарипов") == "SHARIPOV"


def test_the_passports_own_latin_spelling_wins() -> None:
    """It is what the document is checked against; a transliteration of the
    Cyrillic can differ from it by a letter."""
    lines = mrz.build(surname="Хужаев", name="Умид", citizenship="Узбекистан",
                      born=date(1990, 1, 1), gender="M", number="AA1234567",
                      surname_latin="KHUJAEV", name_latin="UMID")
    assert "KHUJAEV<<UMID" in lines[0]


def test_a_space_or_a_hyphen_in_a_name_becomes_the_filler() -> None:
    assert mrz.latin("Кара-Мурза") == "KARA<MURZA"
    assert mrz.latin("АННА МАРИЯ") == "ANNA<MARIIA"


def test_a_name_too_long_for_the_line_is_cut_not_wrapped() -> None:
    line = mrz.name_line("А" * 40, "Б" * 40, "TJK")
    assert len(line) == 44


# ------------------------------------------------------------ the countries
def test_the_countries_our_workers_come_from() -> None:
    assert mrz.country_of("Республика Таджикистан") == "TJK"
    assert mrz.country_of("Узбекистан") == "UZB"
    assert mrz.country_of("Туркменистан") == "TKM"
    assert mrz.country_of("Кыргызстан") == "KGZ"
    assert mrz.country_of("Российская Федерация") == "RUS"


def test_a_code_already_given_is_taken_as_it_is() -> None:
    assert mrz.country_of("TJK") == "TJK"
    assert mrz.country_of("uzb") == "UZB"


def test_a_country_nobody_knows_is_left_blank_rather_than_guessed() -> None:
    """A wrong country code makes the line's check digit wrong as well."""
    assert mrz.country_of("Атлантида") == ""
    assert mrz.country_of("") == ""


# ---------------------------------------------------------- what is missing
def test_a_value_nobody_has_is_filled_with_the_standards_own_blank() -> None:
    """«<», which is what an absent value looks like — never a guess."""
    line = mrz.data_line("", "", None, "", None, "")
    assert line.startswith("<" * 9)
    assert len(line) == 44
    assert "19" not in line, "туғилган сана ўйлаб топилди"


def test_an_unknown_sex_is_the_filler_not_a_choice() -> None:
    assert mrz.data_line("A1", "TJK", None, "", None)[20] == "<"
    assert mrz.data_line("A1", "TJK", None, "Мужской", None)[20] == "M"
    assert mrz.data_line("A1", "TJK", None, "Женский", None)[20] == "F"


# ------------------------------------------- and it reaches the office form
def test_the_zone_is_a_field_the_office_can_place() -> None:
    from src.pdf.universal_fields import CATALOGUE, MRZ, UniversalData, values

    assert MRZ in CATALOGUE
    said = values(UniversalData(
        surname="Исоев", name="Аслидин", citizenship="Республика Таджикистан",
        birth_date=date(1999, 7, 25), gender="Мужской",
        pass_number="405847273", pass_expires=date(2035, 1, 17),
        pass_pin="50707994120019"))
    lines = said[MRZ].split("\n")
    assert len(lines) == 2
    assert all(len(line) == 44 for line in lines)
    assert lines[0].startswith("P<TJKISOEV<<ASLIDIN")


@pytest.mark.parametrize("case", ["", "   "])
def test_a_worker_with_no_documents_gives_no_zone_at_all(case) -> None:
    """A strip of filler is worse than no strip.

    This used to return a well-formed 44-character pair whatever it was
    given, and the office found the result on a printed form: two rows
    reading «<<<<<<<<<0<<<<<<<<<0…», which carry no information and are not
    a valid zone either, since the numbers behind the check digits are
    absent. With nothing to build from, nothing is printed.
    """
    from src.pdf.universal_fields import MRZ_KEYS, UniversalData, values

    said = values(UniversalData(surname=case, pass_number=case))
    assert all(said[key] == "" for key in MRZ_KEYS)


def test_a_zone_that_is_built_at_all_is_built_whole() -> None:
    """The guard above only silences it — it never half-builds one."""
    from src.pdf.universal_fields import MRZ, MRZ_1, MRZ_2, UniversalData, values

    said = values(UniversalData(surname="Исоев", pass_number="405847273"))
    assert said[MRZ].split("\n") == [said[MRZ_1], said[MRZ_2]]
    assert all(len(line) == 44 for line in said[MRZ].split("\n"))
