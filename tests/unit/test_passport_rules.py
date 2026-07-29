"""A Tajik passport on a Russian form: no серия, and «кем выдан» in Russian.

The office fills these for its Tajik drivers and labourers every day, and both
rules were being broken on every document at once — «TJK406576690» where the
passport number goes, and the issuing office still in Tajik. Both rules belong
to the passport itself, so these tests come at them from each of the three
directions a passport can arrive from: read off an image, corrected by the
machine-readable zone, and typed in by hand.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from src.domain.company import Company
from src.domain.documents import Passport, Patent
from src.domain.employee import Employee
from src.domain.passport_rules import issuer_in_russian, normalise_document
from src.services.field_extractor import build_values
from src.services.manual_entry import build_employee


def _tajik(**over) -> Passport:
    fields = dict(surname="САИДОВ", name="ФИРУЗ", patronymic="САИДОВИЧ",
                  nationality="ТАДЖИКИСТАН", series="TJK", number="406576690",
                  birth_date=date(1990, 5, 4), issue_date=date(2019, 3, 12),
                  issued_by="ХШБ ВКД ҶТ")
    fields.update(over)
    return Passport(**fields)


# ------------------------------------------------------------- серия/номер


@pytest.mark.parametrize("series, number", [
    ("TJK", "406576690"),          # the country code read as a серия
    ("", "TJK406576690"),          # ...or glued to the front of the number
    ("", "TJK 406576690"),
    ("ТЖК", "406 576 690"),        # read in Cyrillic, printed with spaces
    ("", "406576690"),             # already right — must stay right
])
def test_a_tajik_passport_is_only_its_nine_digits(series, number) -> None:
    passport = _tajik(series=series, number=number)
    assert passport.series is None, "a Tajik passport has no серия"
    assert passport.number == "406576690"


def test_the_series_box_is_left_empty_on_the_form() -> None:
    """«Паспорт серия деган жой бўш қолсин» — and the number stands alone."""
    passport = _tajik()
    assert (passport.series or "") == ""
    assert f"{passport.series or ''}{passport.number}" == "406576690"


@pytest.mark.parametrize("nationality", ["ТАДЖИКИСТАН", "Таджикистан",
                                         "ТОҶИКИСТОН", "TJK", ""])
def test_it_holds_however_the_citizenship_was_written(nationality) -> None:
    assert _tajik(nationality=nationality).number == "406576690"


@pytest.mark.parametrize("series, number, citizenship", [
    ("AA", "1234567", "УЗБЕКИСТАН"),
    ("FB", "9876543", "КИРГИЗИЯ"),
    ("AN", "1122334", "КАЗАХСТАН"),
])
def test_a_passport_that_does_have_a_series_keeps_it(series, number,
                                                     citizenship) -> None:
    """Only Tajikistan is the exception — nobody else's серия may be dropped."""
    passport = Passport(surname="КАРИМОВ", name="АЗИЗ", nationality=citizenship,
                        series=series, number=number)
    assert passport.series == series
    assert passport.number == number


def test_a_country_code_is_never_a_series() -> None:
    """Even where the citizenship never reached the model."""
    assert normalise_document("UZB", "1234567", None)[0] is None
    assert normalise_document("KGZ", "9876543", "")[0] is None


def test_the_rule_survives_being_applied_twice() -> None:
    once = _tajik()
    twice = Passport.model_validate(once.model_dump())
    assert (twice.series, twice.number) == (once.series, once.number)
    assert twice.issued_by == once.issued_by


# --------------------------------------------------------------- кем выдан


@pytest.mark.parametrize("tajik, russian", [
    ("ХШБ ВКД ҶТ", "ПРС МВД РТ"),       # the office's own workers' passports
    ("ХШБ ВКД ЧТ", "ПРС МВД РТ"),       # ҶТ typed as ЧТ
    ("ХШБ РВКД ҶТ", "ПРС УМВД РТ"),
    ("ВКД ҶТ", "МВД РТ"),
    ("ШВКД дар Хуҷанд", "ОМВД в Худжанд"),
    ("ХШБ дар ш. Душанбе", "ПРС в ш. Душанбе"),
    ("ХШБ ФР", "ПРС РФ"),
    ("Хадамоти Шиносномавию Бақайдгирии Вазорати Корҳои Дохилӣ", "ПРС МВД"),
    ("Вазорати корҳои дохилии Ҷумҳурии Тоҷикистон", "МВД РТ"),
])
def test_the_issuing_office_is_written_in_russian(tajik, russian) -> None:
    assert issuer_in_russian(tajik) == russian
    assert _tajik(issued_by=tajik).issued_by == russian


@pytest.mark.parametrize("printed, russian", [
    # Кыргызстан
    ("МКК", "ГРС"), ("СӨМ", "МЦР"), ("SRS", "ГРС"),
    ("SAIRT", "ГАИРТ"), ("MDD", "МЦР"),
    ("Мамлекеттик Каттоо Кызматы", "ГРС"),
    # Ўзбекистон
    ("IIV", "МВД"), ("IIB", "УВД"), ("TRIB", "МРЭО"),
    ("YHXB", "УБДД"), ("PSC", "ЦГУ"),
    # Україна
    ("СГІРФО", "СГИРФО"), ("ВГІРФО", "ВГИРФО"),
    ("МРЕВ", "МРЭО"), ("ВРЕР", "ОРЭР"),
    # Moldova · Georgia · Қазақстан
    ("ASP", "АОУ"),
    ("Ministry of Justice of Georgia", "Министерство юстиции Грузии"),
    ("DIA", "ОВД"),
])
def test_the_other_republics_are_written_by_their_initials(printed,
                                                           russian) -> None:
    """The office's own reference table, one row at a time.

    A Russian form names an authority by its initials, so that is what goes in
    — «ХШБ ВКД» is «ПРС МВД», not the four words it stands for.
    """
    assert issuer_in_russian(printed) == russian


def test_no_tajik_letter_reaches_a_russian_form() -> None:
    """ҳ қ ғ ӣ ӯ ҷ do not exist in Russian; nothing may carry them through."""
    issued = issuer_in_russian("Шӯъбаи Қӯрғонтеппаи ҒБ")
    assert not set(issued) & set("ҳҲқҚғҒӣӢӯӮҷҶ"), issued


@pytest.mark.parametrize("tajik, russian", [
    ("Ҷамоати Ҷаббор Расулов", "Джамоати Джаббор Расулов"),
    ("ТОҶИКИСТОН", "ТАДЖИКИСТАН"),
    ("Ҷумҳурӣ", "Джумхури"),
])
def test_dzh_is_two_letters_in_russian(tajik, russian) -> None:
    """«ҷ» is «дж», not «ч» — Тоҷикистон is ТАДЖИКИСТАН, not ТОЧИКИСТОН."""
    assert issuer_in_russian(tajik) == russian


def test_an_abbreviation_nobody_listed_is_left_readable() -> None:
    """What the dictionary does not know it does not invent.

    Expanding «ШБ 42» is the vision model's job — it knows these documents and
    there is one such office per district. A wrong guess here would put the
    wrong authority on a migration form, so the letters are simply carried
    through in Russian script for the operator to see.
    """
    assert issuer_in_russian("ШБ 42") == "ШБ 42"


def test_an_office_named_twice_is_not_written_twice() -> None:
    """Two entries landing on the same word must not print it twice."""
    assert issuer_in_russian("ВКД ВКД ҶТ") == "МВД РТ"


@pytest.mark.parametrize("value, expected", [
    ("MIA 4102", "МВД 4102"),          # Uzbek passports still translate
    ("PSC", "ЦГУ"),
    ("МВД РОССИИ", "МВД РОССИИ"),      # Russian already — left alone
    ("ОВД г. Душанбе", "ОВД г. Душанбе"),
    ("", ""),
])
def test_the_other_passports_are_unaffected(value, expected) -> None:
    assert issuer_in_russian(value) == expected


# ------------------------------------------------- every way a passport arrives


def test_a_passport_typed_by_hand_obeys_the_same_rules() -> None:
    """«Қўлда тўлдириш» — the operator may still type the code out of habit."""
    employee = build_employee({
        "surname": "САИДОВ", "name": "ФИРУЗ", "patronymic": "САИДОВИЧ",
        "citizenship": "ТАДЖИКИСТАН", "passport_series": "TJK",
        "passport_number": "406576690", "passport_issued_by": "ХШБ ВКД ҶТ",
        "birth_date": "04.05.1990", "passport_issue_date": "12.03.2019",
    }, uuid4(), contract_date=date(2026, 7, 29))
    assert employee.passport.series is None
    assert employee.passport.number == "406576690"
    assert employee.passport.issued_by == "ПРС МВД РТ"


def test_the_machine_readable_zone_cannot_put_the_code_back() -> None:
    """The zone's values win over the model's — but not over the rules.

    :meth:`OcrService._with_mrz` used to copy them in without revalidating,
    and the zone is exactly where a country code comes from.
    """
    from src.ocr.service import OcrService

    class _Answer:
        text = ""
        fields = {"mrz_line1": "", "mrz_line2": ""}

    read = _tajik(series=None, number="")
    verified = OcrService._with_mrz(read, _Answer())      # no zone: unchanged
    assert verified.series is None

    revalidated = Passport.model_validate(
        {**read.model_dump(), "series": "TJK", "number": "TJK406576690"})
    assert revalidated.series is None
    assert revalidated.number == "406576690"


def test_the_mvd_form_gets_a_blank_series_and_a_bare_number() -> None:
    """The end of the road: what actually lands in the boxes of Приложение 7."""
    passport = _tajik()
    company = Company(name="ООО СФЕРА", internal_code="sfera", okved="41.20",
                      ogrn="1234567890123", inn="7701234567",
                      address_index="115035", address_text="г. Москва",
                      director_fio="ГОРИН А. Э.", template_path=Path("x.pdf"))
    employee = Employee(
        company_id=company.id, passport=passport,
        patent=Patent(series="77", number="2600314661",
                      profession="ПОДСОБНЫЙ РАБОЧИЙ"),
        profession="ПОДСОБНЫЙ РАБОЧИЙ", contract_date=date(2026, 7, 29))

    values = build_values(employee, company, form_date=date(2026, 7, 29),
                          reg_number=1)
    assert values.get("employee.passport.series", "") == ""
    assert values["employee.passport.number"] == "406576690"
    assert values["employee.passport.issued_by"] == "ПРС МВД РТ"
    assert "TJK" not in " ".join(values.values())


# ------------------------------------------------- серия is never translated
def test_a_latin_series_that_was_carried_into_cyrillic_comes_back():
    """«FA» must never reach a form as «ФА» — the office's own report."""
    from src.domain.passport_rules import series_in_latin

    assert series_in_latin("ФА") == "FA"
    assert series_in_latin("ФВ") == "FB"
    assert series_in_latin("ФБ") == "FB"
    assert series_in_latin("С") == "C"
    assert series_in_latin("АС") == "AC"


def test_a_series_already_in_latin_is_left_alone():
    from src.domain.passport_rules import series_in_latin

    for value in ("FA", "FB", "C", "AA", "KG", "MP"):
        assert series_in_latin(value) == value


def test_a_russian_digit_series_is_not_touched():
    from src.domain.passport_rules import series_in_latin

    assert series_in_latin("4512") == "4512"


def test_the_form_gets_the_series_in_latin():
    assert normalise_document("ФА", "1234567", "УЗБЕКИСТАН") == ("FA", "1234567")


def test_a_cyrillic_series_glued_to_the_number_comes_back_too():
    assert normalise_document(None, "ФА1234567", "УЗБЕКИСТАН")[1] == "FA1234567"


def test_the_tajik_rule_still_wins_over_the_latin_one():
    """No серия at all, whatever letters the reader put in the box."""
    assert normalise_document("ФА", "406576690", "ТАДЖИКИСТАН") == \
        (None, "406576690")


def test_a_passport_built_by_hand_obeys_it():
    from src.domain.documents import Passport

    passport = Passport(surname="ИВАНОВ", name="ИВАН", series="ФА",
                        number="1234567", nationality="УЗБЕКИСТАН")
    assert passport.series == "FA"
