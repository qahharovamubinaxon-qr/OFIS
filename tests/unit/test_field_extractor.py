"""Business-rule tests for the field flattener (marks 11, 15, 16)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

from src.domain.company import Company
from src.domain.documents import Passport, Patent
from src.domain.employee import Employee
from src.services.field_extractor import DEFAULT_PROFESSION, build_values, plus_one_year


def _emp(profession: str = DEFAULT_PROFESSION) -> Employee:
    return Employee(
        company_id=uuid4(),
        passport=Passport(
            surname="РАСУЛОВ", name="МУСТАФО", patronymic="АЗИЗЖОН УГЛИ",
            nationality="УЗБЕКИСТАН", number="5512345678",
            birth_date=date(1992, 3, 15), issue_date=date(2019, 6, 20), issued_by="МВД",
        ),
        patent=Patent(number="2612345678", series="77", profession=profession,
                      issue_date=date(2026, 5, 10), issued_by="ОВМ"),
        profession=profession, contract_date=date(2026, 7, 21),
    )


def _company() -> Company:
    return Company(name="ИП", internal_code="G1", okved="46.21.19", ogrn="315080100000587",
                   inn="080100230802", address_index="111677", address_text="МОСКВА",
                   director_fio="ГОРДИЕНКО", template_path=Path("t.pdf"))


def test_plus_one_year_and_leap() -> None:
    assert plus_one_year(date(2026, 5, 10)) == date(2027, 5, 10)
    assert plus_one_year(date(2024, 2, 29)) == date(2025, 3, 1)


def test_patent_expiry_is_issue_plus_year() -> None:
    v = build_values(_emp(), _company(), form_date=date(2026, 7, 23), reg_number=345)
    assert v["patent.from.y"][:4] == "2026"
    assert v["patent.to.y"][:4] == "2027"


def test_fio_citizenship_and_regnumber() -> None:
    v = build_values(_emp(), _company(), form_date=date(2026, 7, 23), reg_number=345)
    assert v["employee.fio_citizenship"] == "РАСУЛОВ МУСТАФО АЗИЗЖОН УГЛИ, УЗБЕКИСТАН"
    assert v["doc.reg_number"] == "345"


def test_default_profession_is_not_written() -> None:
    # default → leave the pre-printed template text (no field emitted)
    v = build_values(_emp(), _company(), form_date=date(2026, 7, 23), reg_number=1)
    assert "employee.profession" not in v


def test_custom_profession_is_written() -> None:
    v = build_values(_emp(), _company(), form_date=date(2026, 7, 23),
                     reg_number=1, profession="ВОДИТЕЛЬ")
    assert v["employee.profession"] == "ВОДИТЕЛЬ"
