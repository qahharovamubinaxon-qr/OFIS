"""Domain model validation tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.domain.company import Company
from src.domain.documents import Passport, Patent
from src.domain.employee import Employee
from src.domain.enums import ContractType, EmployerType


def _company() -> Company:
    return Company(
        name="ИП ГОРДИЕНКО А.А.",
        internal_code="GORDIENKO",
        employer_type=EmployerType.IP,
        okved="46.21.19",
        ogrn="315080100000587",
        inn="080100230802",
        address_index="111677",
        address_text="МОСКВА УЛ. ВЕРТОЛЁТЧИКОВ Д4 К2",
        director_fio="ГОРДИЕНКО АЛЕКСЕЙ АНАТОЛЬЕВИЧ",
        template_path=Path("templates/mvd_prilozhenie_7/template.pdf"),
    )


def test_passport_cleans_whitespace_and_numbers() -> None:
    p = Passport(surname="  АЗИМОВ ", name="АЛИДЖОН", number="40 25 112331")
    assert p.surname == "АЗИМОВ"
    assert p.number == "4025112331"  # spaces stripped from numbers


def test_company_normalizes_inn_and_ogrn() -> None:
    c = _company()
    assert c.inn == "080100230802"
    assert c.ogrn == "315080100000587"
    assert c.okved == "46.21.19"


def test_company_rejects_bad_inn() -> None:
    with pytest.raises(PydanticValidationError):
        Company(
            name="X", internal_code="X", okved="46.21", ogrn="315080100000587",
            inn="123", address_index="1", address_text="a",
            director_fio="Y", template_path=Path("t.pdf"),
        )


def test_employee_output_basename_and_full_name() -> None:
    emp = Employee(
        company_id=uuid4(),
        passport=Passport(surname="АЗИМОВ", name="АЛИДЖОН", patronymic="АБДУВОХИДОВИЧ", number="4025112331"),
        patent=Patent(number="26003 14661", profession="ПОДСОБНЫЙ РАБОЧИЙ"),
        profession="ПОДСОБНЫЙ РАБОЧИЙ",
        contract_type=ContractType.LABOR,
        contract_date=date(2026, 7, 21),
    )
    assert emp.full_name == "АЗИМОВ АЛИДЖОН АБДУВОХИДОВИЧ"
    assert emp.output_basename() == "АЗИМОВ_АЛИДЖОН"
