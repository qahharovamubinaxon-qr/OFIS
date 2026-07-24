"""Registration address + registration generation end-to-end (real SQLite + PDF)."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest

from src.app import build_container
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender
from src.services.registration_address_service import RegistrationAddressService
from src.services.registration_service import RegistrationService
from src.services.registration_values import build_registration_values

ROOT = Path(__file__).resolve().parents[2]
HAS_TEMPLATE = (ROOT / "templates" / "registration" / "mapping.v1.json").exists()


@pytest.fixture()
def container(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    from src.config import paths

    paths.data_dir.cache_clear()
    return build_container()


def _passport() -> Passport:
    return Passport(
        surname="ПАЛВАНОВ", name="ДОВЛЕТГЕЛДИ", patronymic="БАЙРАМОВИЧ",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE, number="046688", series="A2",
        birth_date=date(1990, 5, 15), issue_date=date(2023, 3, 13), expiry_date=date(2028, 3, 12),
    )


def _patent() -> Patent:
    return Patent(
        number="26003", series="77", profession="ПОДСОБНЫЙ РАБОЧИЙ",
        issue_date=date(2026, 5, 10),
        holder_surname="ПАЛВАНОВ", holder_name="ДОВЛЕТГЕЛДИ",
        holder_patronymic="БАЙРАМОВИЧ", holder_citizenship="ТУРКМЕНИСТАН",
    )


def test_values_take_names_from_patent_and_gender_from_passport() -> None:
    # passport names deliberately wrong (as a non-Cyrillic misread would be)
    passport = _passport().model_copy(update={"surname": "WRONG", "name": "WRONG"})
    v = build_registration_values(passport, _patent(), registration_expiry=date(2026, 10, 12))
    assert v["reg.surname"] == "ПАЛВАНОВ"  # from patent
    assert v["reg.citizenship"] == "ТУРКМЕНИСТАН"
    assert v["reg.gender.male"] == "V" and "reg.gender.female" not in v
    # registration expiry lands on both the page-1 and page-2 date fields
    assert v["reg.stay_until.y"] == "2026-10-12"
    assert v["reg.registered_until.y"] == "2026-10-12"


@pytest.mark.skipif(not HAS_TEMPLATE, reason="registration template missing")
def test_seed_and_generate_registration(container) -> None:
    addresses = container.resolve(RegistrationAddressService)
    reg = container.resolve(RegistrationService)
    assert addresses.count() == 1
    address = addresses.list()[0]

    result = reg.generate(
        _passport(), _patent(), address, registration_expiry=date(2026, 10, 12)
    )
    assert result.pdf_path.exists()
    assert result.pdf_path.name == "ПАЛВАНОВ_ДОВЛЕТГЕЛДИ.pdf"

    doc = fitz.open(str(result.pdf_path))
    page1 = "".join(doc[0].get_text().split())
    page2 = "".join(doc[1].get_text().split())
    doc.close()
    assert "ПАЛВАНОВ" in page1
    assert "ТУРКМЕНИСТАН" in page1
    assert "2026" in page2  # Поставлен на учет до year
