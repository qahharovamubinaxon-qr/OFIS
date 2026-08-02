"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — the eight mapped firms."""

from __future__ import annotations

import tempfile
from datetime import date

import fitz
import pytest
from src.config import paths
from src.pdf.trud8_renderer import Trud8Data, output_stem, values


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


_WORKER = dict(
    surname="КОРЁГДИЕВ", name="ТУЛКИНЖОН", patronymic="ТЕША УГЛИ",
    gender="male", citizenship="УЗБЕКИСТАН", birth_date=date(1994, 11, 10),
    pass_series="FA", pass_number="2533791", pass_issued=date(2021, 4, 12),
    pass_issued_by="MIA OF UZBEKISTAN", pat_series="77",
    pat_number="250695887", pat_blank_series="ПР",
    pat_blank_number="5094937", pat_issued=date(2026, 7, 1),
    profession="Разнорабочий", deal_date=date(2026, 8, 2))


def test_the_bundle_ships_all_eight_firms() -> None:
    from src.services.trud8_service import bundled_dir

    firms = sorted(p.name for p in bundled_dir().iterdir() if p.is_dir())
    assert len(firms) == 8
    assert "МОНОТЕК СТРОЙ" in firms and "БАХАМ" in firms
    for firm in bundled_dir().iterdir():
        assert (firm / "td.pdf").exists() and (firm / "td.json").exists()


def test_values_write_the_samples_manner() -> None:
    made = values(Trud8Data(**_WORKER))
    assert made["surname"] == "Корёгдиев"
    assert made["fio"] == "Корёгдиев Тулкинжон Теша Угли"
    assert made["gender"] == "Мужской"
    assert made["deal_date"] == "02.08.2026"
    assert made["pat_blank_series"] == "ПР"


def test_generate_replaces_the_old_worker_on_both_papers() -> None:
    from src.services.trud8_service import Trud8Service, firms_dir

    service = Trud8Service()
    firms = {f.name: f for f in service.firms()}
    assert len(firms) == 8, "seeding lost a firm"
    assert firms_dir().exists()

    monotek = firms["МОНОТЕК СТРОЙ"]
    result = service.generate(Trud8Data(**_WORKER), monotek)
    assert len(result.saved) == 2                # ТД and УВ
    assert result.saved[0].name.startswith("КОРЁГДИЕВ_ТУЛКИНЖОН")
    for out in result.saved:
        with fitz.open(str(out)) as doc:
            ink = "".join(p.get_text() for p in doc).replace("\xa0", " ")
        assert "Корёгдиев" in ink, f"{out.name}: the new worker is missing"
        assert "Хурсанов" not in ink and "Шосулаймонов" not in ink, \
            f"{out.name}: the sample's old worker survived"
        assert "02.08.2026" in ink


def test_a_firm_without_uv_still_prints_the_td() -> None:
    from src.services.trud8_service import Trud8Service

    service = Trud8Service()
    firms = {f.name: f for f in service.firms()}
    obshestroy = firms["ОБЩЕСТРОЙ-А"]
    assert not (obshestroy / "uv.pdf").exists()
    result = service.generate(Trud8Data(**_WORKER), obshestroy)
    assert len(result.saved) == 1
    assert result.saved[0].name.endswith("_ТД.pdf")


def test_a_dragged_slot_overrides_its_own_occurrence(tmp_path) -> None:
    from src.services.trud8_service import Trud8Service

    service = Trud8Service()
    firms = {f.name: f for f in service.firms()}
    piter = firms["ПИТЕР"]
    service.save_layout(piter, "td", {"fields": {}})
    assert service.layout(piter, "td")["fields"] == {}
    slots = service.slots(piter, "td")
    assert slots and all("clear" in s for s in slots)


def test_the_filename_is_surname_name() -> None:
    assert output_stem(Trud8Data(**_WORKER)) == "КОРЁГДИЕВ_ТУЛКИНЖОН"
