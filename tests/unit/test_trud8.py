"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — the office's own blanks, the office's own map."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.common.errors import ValidationError
from src.config import paths
from src.pdf.trud8_fields import CATALOGUE, SAMPLES, Field
from src.pdf.trud8_renderer import Trud8Data, output_stem, render, values


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
    pat_valid_to=date(2027, 5, 27), profession="Разнорабочий",
    deal_date=date(2026, 8, 2), work_address="г. Москва, ул. Мира, д. 1")


def _blank(pages: int = 2) -> Path:
    """A bare A4 the office might upload."""
    made = Path(tempfile.mkdtemp()) / "blank.pdf"
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=595, height=842)
    doc.save(str(made))
    doc.close()
    return made


def _spans(pdf: bytes, page: int = 1) -> list[dict]:
    found = []
    with fitz.open("pdf", pdf) as doc:
        for block in doc[page - 1].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    # PyMuPDF hands back the embedded font's own space
                    span["text"] = " ".join(span["text"].split())
                    found.append(span)
    return found


# --------------------------------------------------------------- values
def test_every_meaning_in_the_list_can_be_filled() -> None:
    made = values(Trud8Data(**_WORKER))
    missing = [key for key in CATALOGUE if not made.get(key)]
    assert missing == [], f"тўлдирилмаган маънолар: {missing}"
    assert sorted(SAMPLES) == sorted(CATALOGUE), "намуна матн етишмайди"


def test_values_read_the_way_the_papers_are_typed() -> None:
    made = values(Trud8Data(**_WORKER))
    assert made["fio"] == "Абдулхаков Сунатулло Ибодуллоевич"
    assert made["fio_upper"] == "АБДУЛХАКОВ СУНАТУЛЛО ИБОДУЛЛОЕВИЧ"
    assert made["gender"] == "Мужской"
    assert made["birth_date"] == "08.12.1990"
    assert (made["birth_day"], made["birth_month"], made["birth_year"]) \
        == ("08", "12", "1990")
    assert made["pass_full"] == "P 402543058"
    assert made["pat_full"] == "50 2600164027"
    assert made["pat_valid_to"] == "27.05.2027"
    assert made["deal_month_ru"] == "августа"
    assert made["deal_year_short"] == "26"
    assert output_stem(Trud8Data(**_WORKER)) == "АБДУЛХАКОВ_СУНАТУЛЛО"


def test_a_field_survives_being_written_down() -> None:
    made = Field(key="fio", page=2, x=0.31, baseline=0.42, size=0.0155,
                 bold=True, serif=False, colour=(1.0, 0.0, 0.0))
    again = Field.from_dict(made.as_dict())
    assert again == made
    assert again.label() == CATALOGUE["fio"]
    assert again.sample() == SAMPLES["fio"]


# --------------------------------------------------------------- render
def test_the_worker_lands_where_the_office_put_him() -> None:
    fields = [Field(key="fio", page=1, x=0.20, baseline=0.30, size=0.0150),
              Field(key="pass_full", page=2, x=0.55, baseline=0.70,
                    size=0.0120)]
    pdf = render(Trud8Data(**_WORKER), _blank(), fields)

    first = _spans(pdf, 1)
    assert [s["text"] for s in first] == ["Абдулхаков Сунатулло Ибодуллоевич"]
    assert first[0]["origin"][0] == pytest.approx(0.20 * 595, abs=1.0)
    assert first[0]["origin"][1] == pytest.approx(0.30 * 842, abs=1.0)
    assert first[0]["size"] == pytest.approx(0.0150 * 842, abs=0.3)

    second = _spans(pdf, 2)
    assert [s["text"] for s in second] == ["P 402543058"]
    assert second[0]["origin"][0] == pytest.approx(0.55 * 595, abs=1.0)


def test_colour_and_weight_are_the_office_s_choice() -> None:
    fields = [Field(key="surname", page=1, x=0.2, baseline=0.2, size=0.02,
                    colour=(1.0, 0.0, 0.0), bold=True),
              Field(key="name", page=1, x=0.2, baseline=0.3, size=0.02)]
    spans = {s["text"]: s for s in _spans(render(Trud8Data(**_WORKER),
                                                _blank(1), fields))}
    assert spans["Абдулхаков"]["color"] == 0xFF0000
    assert spans["Сунатулло"]["color"] == 0x000000
    assert spans["Абдулхаков"]["font"] != spans["Сунатулло"]["font"]


def test_empty_values_and_missing_pages_print_nothing() -> None:
    quiet = dict(_WORKER, patronymic="")
    fields = [Field(key="patronymic", page=1, x=0.2, baseline=0.2, size=0.02),
              Field(key="fio", page=9, x=0.2, baseline=0.3, size=0.02)]
    assert _spans(render(Trud8Data(**quiet), _blank(1), fields)) == []


# -------------------------------------------------------------- service
def _service():
    from src.services.trud8_service import Trud8Service

    return Trud8Service()


def test_a_firm_is_a_name_two_blanks_and_its_own_map() -> None:
    service = _service()
    firm = service.add_firm("МОНОТЕК СТРОЙ")
    assert service.firms() == [firm]
    assert service.blank(firm, "td") is None
    service.set_blank(firm, "td", _blank(2))
    assert service.pages(firm, "td") == 2

    service.add_field(firm, "td", "fio", page=1)
    service.add_field(firm, "td", "pat_number", page=2)
    assert [f.key for f in service.fields(firm, "td")] == ["fio", "pat_number"]

    service.move_fields(firm, "td", {"fio#0": [0.31, 0.44, 0.017]})
    service.restyle_field(firm, "td", 0, colour=(0.0, 0.0, 1.0), bold=True,
                          serif=False)
    kept = service.fields(firm, "td")[0]
    assert (kept.x, kept.baseline, kept.size) == (0.31, 0.44, 0.017)
    assert kept.colour == (0.0, 0.0, 1.0) and kept.bold and not kept.serif

    service.remove_field(firm, "td", 0)
    assert [f.key for f in service.fields(firm, "td")] == ["pat_number"]


def test_only_meanings_from_the_list_can_be_placed() -> None:
    service = _service()
    firm = service.add_firm("АНЕФ")
    with pytest.raises(ValidationError):
        service.add_field(firm, "td", "нима эди", page=1)
    with pytest.raises(ValidationError):
        service.set_blank(firm, "td", Path("yoq.pdf"))


def test_generate_prints_both_papers_from_the_office_s_blanks() -> None:
    service = _service()
    firm = service.add_firm("ТУЛА СЕРВИС")
    service.set_blank(firm, "td", _blank(1))
    service.set_blank(firm, "uv", _blank(1))
    service.add_field(firm, "td", "fio")
    service.add_field(firm, "uv", "pat_number")

    result = service.generate(Trud8Data(**_WORKER), firm)
    assert [p.name for p in result.saved] == \
        ["АБДУЛХАКОВ_СУНАТУЛЛО_ТД.pdf", "АБДУЛХАКОВ_СУНАТУЛЛО_УВ.pdf"]
    td, uv = (p.read_bytes() for p in result.saved)
    assert "Абдулхаков" in _spans(td)[0]["text"]
    assert _spans(uv)[0]["text"] == "2600164027"

    again = service.generate(Trud8Data(**_WORKER), firm)
    assert again.saved[0].name == "АБДУЛХАКОВ_СУНАТУЛЛО_ТД (2).pdf"


def test_a_firm_without_a_blank_says_so() -> None:
    service = _service()
    firm = service.add_firm("БАХАМ")
    with pytest.raises(ValidationError, match="бланка"):
        service.generate(Trud8Data(**_WORKER), firm)
    with pytest.raises(ValidationError):
        service.generate(Trud8Data(**_WORKER), None)


def test_the_old_bundled_firms_are_thrown_away_once() -> None:
    from src.services.trud8_service import LEGACY_MARK, firms_dir

    old = firms_dir() / "ЭСКИ ФИРМА"
    old.mkdir(parents=True)
    (old / "td.docx").write_bytes(b"old")
    (old / "uv.values.json").write_text("{}", encoding="utf-8")

    service = _service()
    assert service.firms() == []
    assert not old.exists()
    assert (firms_dir() / LEGACY_MARK).exists()

    # the office rebuilds a firm under the very same name — never touched again
    rebuilt = service.add_firm("ЭСКИ ФИРМА")
    (rebuilt / "td.docx").write_text("мени ўчирма", encoding="utf-8")
    assert service.firms() == [rebuilt]
    assert (rebuilt / "td.docx").exists()


def test_nothing_ships_with_the_program_any_more() -> None:
    assert not (paths.templates_dir() / "trud8").exists()
