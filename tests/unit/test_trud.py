"""Трудовой-Уведомления: doc editing, values, firm CRUD."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest

from src.app import build_container
from src.database.repositories.trud_firm_repo import TrudFirmRepository
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender
from src.domain.trud_firm import TrudFirm
from src.services.trud_service import TrudFirmService, TrudService, patent_region


@pytest.fixture()
def container(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    from src.config import paths

    paths.data_dir.cache_clear()
    return build_container()


def _passport() -> Passport:
    return Passport(
        surname="ПАЛВАНОВ", name="ДОВЛЕТГЕЛДИ", patronymic="БАЙРАМОВИЧ",
        nationality="ТУРКМЕНИСТАН", gender=Gender.MALE, series="A2", number="2046688",
        birth_date=date(1990, 5, 15), issue_date=date(2023, 3, 13), issued_by="МВД 14405",
    )


def _patent() -> Patent:
    return Patent(number="2600100957", series="77", profession="ПОДСОБНЫЙ РАБОЧИЙ",
                  issued_by="ГУ МВД РОССИИ ПО Г. МОСКВЕ",
                  blank_series="ПР", blank_number="6164274")


_FONT = Path(__file__).resolve().parents[2] / "resources" / "fonts" / "OfisSans-Regular.ttf"


def _make_trud_template(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="cyr", fontfile=str(_FONT))
    kw = {"fontname": "cyr"}
    page.insert_text((70, 60), "ТРУДОВОЙ ДОГОВОР", fontsize=16, **kw)
    page.insert_text((70, 100), "г. Москва", fontsize=11, **kw)
    page.insert_text((450, 100), "23.07.2026", fontsize=11, **kw)
    page.insert_text(
        (70, 160),
        "Работник: Шарафутдинов Дилмурод Камолидинович, Дата рождения 04.07.1987",
        fontsize=11, **kw,
    )
    page.insert_text((70, 175), "Гражданство Узбекистан Номер FA1315643 Кем выдан МВД 14405",
                     fontsize=11, **kw)
    page.insert_text((70, 240), "1. ПРЕДМЕТ ТРУДОВОГО ДОГОВОРА", fontsize=12, **kw)
    page.insert_text((70, 260), "1.1. в должности: Разнорабочий", fontsize=11, **kw)
    page.insert_text((70, 280), "2.2.1. обязанности: Разнорабочий", fontsize=11, **kw)
    doc.save(str(path))
    doc.close()


def _make_uved_template(path: Path) -> None:
    doc = fitz.open()
    doc.new_page(width=595, height=871)
    doc.new_page(width=595, height=871)
    doc.save(str(path))
    doc.close()


def test_region_derivation() -> None:
    assert patent_region(_patent()) == "Москва"
    mo = _patent().model_copy(update={"issued_by": "ГУ МВД РОССИИ ПО МОСКОВСКОЙ ОБЛАСТИ"})
    assert patent_region(mo) == "Московская область"
    assert patent_region(None) == "Москва"


def test_generate_two_pdfs(tmp_path) -> None:
    trud_tpl = tmp_path / "trud.pdf"
    uved_tpl = tmp_path / "uved.pdf"
    _make_trud_template(trud_tpl)
    _make_uved_template(uved_tpl)
    firm = TrudFirm(name="ООО ТЕСТ", internal_code="test",
                    trud_template_path=trud_tpl, uved_template_path=uved_tpl)

    result = TrudService().generate(
        _passport(), _patent(), firm, form_date=date(2026, 7, 25), output_dir=tmp_path,
    )
    assert result.trud_path.exists() and result.uved_path.exists()
    assert "ТРУДОВОЙ" in result.trud_path.name and "УВЕДОМЛЕНИЕ" in result.uved_path.name

    trud_text = " ".join(fitz.open(str(result.trud_path))[0].get_text().split())
    assert "Палванов Довлетгелди Байрамович" in trud_text
    assert "Шарафутдинов" not in trud_text  # old worker really removed
    assert "25.07.2026" in trud_text and "23.07.2026" not in trud_text
    assert "должности: Подсобный рабочий" in trud_text

    uved = fitz.open(str(result.uved_path))
    p1 = " ".join(uved[0].get_text().split())
    p2 = " ".join(uved[1].get_text().split())
    assert "Палванов" in p1 and "Мужской" in p1
    assert "Туркменистан" in p2 and "2600100957" in p2 and "ПР" in p2
    assert "25.07.2026" in p2  # дата заключения договора


def test_firm_crud(container, tmp_path, monkeypatch) -> None:
    from src.config import paths as p

    monkeypatch.setattr(p, "templates_dir", lambda: tmp_path / "templates")
    trud_tpl = tmp_path / "t.pdf"
    uved_tpl = tmp_path / "u.pdf"
    _make_trud_template(trud_tpl)
    _make_uved_template(uved_tpl)

    svc = TrudFirmService(container.resolve(TrudFirmRepository))
    firm = svc.create("ООО СЕРВИС", "servis", trud_tpl, uved_tpl)
    assert firm.trud_template_path.exists() and firm.uved_template_path.exists()
    assert len(svc.list()) == 1
    svc.archive(firm.id)
    assert svc.list() == []
