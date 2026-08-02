"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — the firms' own Word files, worker swapped."""

from __future__ import annotations

import tempfile
from datetime import date

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
    surname="АБДУЛХАКОВ", name="СУНАТУЛЛО", patronymic="ИБОДУЛЛОЕВИЧ",
    gender="male", citizenship="ТАДЖИКИСТАН", birth_date=date(1990, 12, 8),
    pass_series="P", pass_number="402543058", pass_issued=date(2019, 3, 5),
    pass_issued_by="DIA IN KULOB", pat_series="50",
    pat_number="2600164027", pat_blank_series="ПР",
    pat_blank_number="7805409", pat_issued=date(2026, 5, 28),
    profession="Разнорабочий", deal_date=date(2026, 8, 2))


def _text_of(path) -> str:
    from src.services.trud8_probe import doc_texts

    return "\n".join(doc_texts(path))


def test_the_bundle_ships_all_ten_firms_as_word() -> None:
    from src.services.trud8_service import bundled_dir

    firms = sorted(p.name for p in bundled_dir().iterdir() if p.is_dir())
    assert len(firms) == 10
    assert "МОНОТЕК СТРОЙ" in firms and "ТУЛА СЕРВИС" in firms
    for firm in bundled_dir().iterdir():
        assert (firm / "td.docx").exists()
        assert (firm / "td.values.json").exists()
        assert (firm / "uv.docx").exists()
        assert (firm / "uv.values.json").exists()


def test_generate_swaps_the_worker_inside_word() -> None:
    from src.services.trud8_service import Trud8Service

    service = Trud8Service()
    firms = {f.name: f for f in service.firms()}
    assert len(firms) == 10
    result = service.generate(Trud8Data(**_WORKER), firms["МОНОТЕК СТРОЙ"])
    assert [p.suffix for p in result.saved] == [".docx", ".docx"]
    assert result.saved[0].name.startswith("АБДУЛХАКОВ_СУНАТУЛЛО")
    for out in result.saved:
        ink = _text_of(out)
        assert "Абдулхаков" in ink, f"{out.name}: янги ишчи йўқ"
        assert "Хурсанов" not in ink and "Шосулаймонов" not in ink, \
            f"{out.name}: эски ишчи қолди"
    uv_ink = _text_of(result.saved[1])
    assert "02.08.2026" in uv_ink            # шартнома санаси янгиланди
    assert "01.07.2025" not in uv_ink        # эскиси кетди
    assert "2600164027" in uv_ink            # янги патент рақами


def test_every_firm_loses_its_old_worker() -> None:
    import json

    from src.services.trud8_service import Trud8Service

    service = Trud8Service()
    for firm in service.firms():
        stored = json.loads(
            (firm / "uv.values.json").read_text(encoding="utf-8"))
        old_surname = stored.get("surname", "")
        result = service.generate(Trud8Data(**_WORKER), firm)
        for out in result.saved:
            ink = _text_of(out)
            assert "Абдулхаков" in ink, f"{firm.name}/{out.name}"
            if old_surname and old_surname != "Абдулхаков":
                assert old_surname not in ink, \
                    f"{firm.name}/{out.name}: {old_surname} қолди"


def test_adding_a_word_firm_probes_its_old_worker() -> None:
    from src.services.trud8_service import Trud8Service, bundled_dir

    service = Trud8Service()
    donor = bundled_dir() / "ПИТЕР" / "td.docx"
    made = service.add_firm("ЯНГИ ФИРМА", donor)
    assert (made / "td.docx").exists()
    import json

    found = json.loads((made / "td.values.json").read_text(encoding="utf-8"))
    assert found.get("fio") == "Шодиев Исомидин Ёкубович"
    result = service.generate(Trud8Data(**_WORKER), made)
    assert len(result.saved) == 1
    assert "Шодиев" not in _text_of(result.saved[0])


def test_values_and_filename() -> None:
    made = values(Trud8Data(**_WORKER))
    assert made["fio"] == "Абдулхаков Сунатулло Ибодуллоевич"
    assert made["gender"] == "Мужской"
    assert output_stem(Trud8Data(**_WORKER)) == "АБДУЛХАКОВ_СУНАТУЛЛО"
