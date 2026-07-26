"""СФЕРА: dative names, value building, counters, and 2-page generation."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest

from src.app import build_container
from src.domain.documents import Passport
from src.domain.profession import Profession
from src.services.profession_service import ProfessionService
from src.services.svera_service import SveraService
from src.services.svera_values import build_svera_values, format_reg13
from src.utils.ru_names import to_dative

ROOT = Path(__file__).resolve().parents[2]
HAS_TEMPLATE = (ROOT / "templates" / "svera" / "mapping.v1.json").exists()


@pytest.fixture()
def container(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    from src.config import paths

    paths.data_dir.cache_clear()
    return build_container()


def test_dative_declension() -> None:
    assert to_dative("РАСУЛОВ", "АЗИЗ", "АНВАРОВИЧ") == "Расулову Азизу Анваровичу"
    assert to_dative("ШУКУРОВ", "ЗАРИФ", "СЕВИНОВИЧ") == "Шукурову Зарифу Севиновичу"
    # «угли» patronymics are not declined, and each word is capitalised the way
    # the centre's certificates print them
    assert to_dative("АХМЕДОВ", "ЖАСУР", "БАХТИЯР УГЛИ") == "Ахмедову Жасуру Бахтияр Угли"


def test_reg13_format() -> None:
    assert format_reg13(1800359856150) == "180035 9856150"
    assert format_reg13(1800359856151) == "180035 9856151"


def test_profession_text() -> None:
    p = Profession(name="Арматурщик", grade=5)
    assert p.quoted == "«Арматурщик»"
    # the протокол «Заключение» column reads «5-й разряд»
    assert p.qualification_short == "Арматурщик 5-й разряд"
    assert p.qualification_full == "Арматурщик 5 (пятого) разряда"


def test_values_split_case() -> None:
    p = Passport(surname="ШУКУРОВ", name="ЗАРИФ", patronymic="СЕВИНОВИЧ", number="1")
    v = build_svera_values(
        p.surname, p.name, p.patronymic, Profession(name="Арматурщик"),
        issue_date=date(2023, 11, 6), photo_path=None,
        po_number=3963, udo_number=606, reg13=1800359856150,
    )
    # protocol ФИО is nominative Title-case, certificate ФИО is dative
    assert v["svera.fio_protocol"] == "Шукуров\nЗариф\nСевинович"
    assert v["svera.fio_udo_right"] == "Шукурову Зарифу Севиновичу"
    # the same ПО number heads the protocol and is cited on the certificate
    assert v["svera.protocol_title"] == "ПРОТОКОЛ № ПО3963"
    assert "ПО3963" in str(v["svera.osnovanie"])
    # the certificate number doubles as the protocol's регистрац. №
    assert v["svera.udo_title"] == "УДОСТОВЕРЕНИЕ № 606"
    assert str(v["svera.result"]).splitlines() == ["Сдал,", "606", "180035 9856150"]
    # dates carry exactly one Russian year marker
    assert str(v["svera.date_long_top"]).count("г.") == 1
    assert str(v["svera.prikaz"]).count("г.") == 1


@pytest.mark.skipif(not HAS_TEMPLATE, reason="svera template missing")
def test_seed_and_generate(container) -> None:
    professions = container.resolve(ProfessionService)
    svera = container.resolve(SveraService)
    assert professions.count() == 5
    prof = professions.list()[0]

    passport = Passport(surname="ШУКУРОВ", name="ЗАРИФ", patronymic="СЕВИНОВИЧ", number="1")
    po = svera.next_po_number()
    result = svera.generate(passport, prof, issue_date=date(2023, 11, 6), photo_path=None)

    assert result.pdf_path.exists()
    assert result.pdf_path.name == "ШУКУРОВ_ЗАРИФ.pdf"
    assert result.po_number == po
    doc = fitz.open(str(result.pdf_path))
    assert doc.page_count == 2
    protocol, udo = doc[0].get_text(), doc[1].get_text()
    assert f"ПРОТОКОЛ № ПО{po}" in " ".join(protocol.split())
    assert "Шукурову Зарифу Севиновичу" in " ".join(udo.split())
    # the centre's round stamp is printed on the certificate page
    assert doc[1].get_images(), "stamp/photo images missing on the certificate"
    doc.close()
    # ПО counter advances
    assert svera.next_po_number() == po + 1
