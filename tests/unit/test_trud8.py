"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — the office's own blanks, the office's own map."""

from __future__ import annotations

import os
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
    pass_issued_by="МВД 14505", pat_series="50",
    pat_number="2600164027", pat_blank_series="ПР",
    pat_blank_number="7805409", pat_issued=date(2026, 5, 28),
    pat_valid_to=date(2027, 5, 27),
    pat_issued_by="ГУ МВД России по Московской области",
    profession="Разнорабочий", deal_date=date(2026, 8, 2),
    work_address="г. Москва, ул. Мира, д. 1")


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
    assert made["pass_issued_by"] == "МВД 14505"
    assert made["pat_full"] == "50 2600164027"
    assert made["pat_valid_to"] == "27.05.2027"
    assert made["pat_issued_by"] == "ГУ МВД России по Московской области"
    assert made["deal_month_ru"] == "августа"
    assert made["deal_year_short"] == "26"
    assert output_stem(Trud8Data(**_WORKER)) == "АБДУЛХАКОВ_СУНАТУЛЛО"


def test_the_region_is_read_off_the_patent_series() -> None:
    """«50 2600164027» is a Moscow-region patent — nobody types that again."""
    assert values(Trud8Data(**_WORKER))["pat_region"] == "Московская область"
    assert values(Trud8Data(**dict(_WORKER, pat_series="77")))["pat_region"] \
        == "г. Москва"
    assert values(Trud8Data(**dict(_WORKER, pat_series="")))["pat_region"] == ""


def test_a_field_survives_being_written_down() -> None:
    made = Field(key="fio", page=2, x=0.31, baseline=0.42, size=0.0155,
                 bold=True, font="Calibri", colour=(1.0, 0.0, 0.0))
    again = Field.from_dict(made.as_dict())
    assert again == made
    assert again.label() == CATALOGUE["fio"]
    assert again.sample() == SAMPLES["fio"]


def test_a_map_saved_before_faces_could_be_chosen_still_opens() -> None:
    """Maps written when a text was only «serif or not»."""
    assert Field.from_dict({"key": "fio", "serif": True}).font \
        == "Times New Roman"
    assert Field.from_dict({"key": "fio", "serif": False}).font == "Arial"


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


@pytest.mark.skipif(os.name != "nt", reason="Windows fonts")
def test_the_face_is_the_one_the_office_picked() -> None:
    fields = [Field(key="surname", page=1, x=0.2, baseline=0.2, size=0.02,
                    font="Times New Roman"),
              Field(key="name", page=1, x=0.2, baseline=0.3, size=0.02,
                    font="Arial"),
              Field(key="patronymic", page=1, x=0.2, baseline=0.4, size=0.02,
                    font="Courier New", bold=True)]
    spans = {s["text"]: s["font"] for s in
             _spans(render(Trud8Data(**_WORKER), _blank(1), fields))}
    assert "Times" in spans["Абдулхаков"]
    assert "Arial" in spans["Сунатулло"]
    assert "Courier" in spans["Ибодуллоевич"]
    assert "Bold" in spans["Ибодуллоевич"]


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

    service.save_fields(firm, "td", [
        Field(key="fio", page=1, x=0.31, baseline=0.44, size=0.017,
              bold=True, font="Calibri", colour=(0.0, 0.0, 1.0)),
        Field(key="pat_number", page=2)])
    kept = service.fields(firm, "td")
    assert [f.key for f in kept] == ["fio", "pat_number"]
    assert (kept[0].x, kept[0].baseline, kept[0].size) == (0.31, 0.44, 0.017)
    assert kept[0].colour == (0.0, 0.0, 1.0) and kept[0].bold
    assert kept[0].font == "Calibri"

    service.save_fields(firm, "td", kept[1:])
    assert [f.key for f in service.fields(firm, "td")] == ["pat_number"]


def test_only_meanings_from_the_list_can_be_placed() -> None:
    service = _service()
    firm = service.add_firm("АНЕФ")
    with pytest.raises(ValidationError):
        service.save_fields(firm, "td", [Field(key="нима эди")])
    with pytest.raises(ValidationError):
        service.set_blank(firm, "td", Path("yoq.pdf"))


def test_generate_prints_both_papers_from_the_office_s_blanks() -> None:
    service = _service()
    firm = service.add_firm("ТУЛА СЕРВИС")
    service.set_blank(firm, "td", _blank(1))
    service.set_blank(firm, "uv", _blank(1))
    service.save_fields(firm, "td", [Field(key="fio")])
    service.save_fields(firm, "uv", [Field(key="pat_number")])

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


# --------------------------------------------------------------- window
@pytest.fixture()
def editor_window(monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def _png(pages: int = 2) -> list[bytes]:
    with fitz.open(str(_blank(pages))) as doc:
        return [page.get_pixmap(dpi=60).tobytes("png") for page in doc]


def _answers(monkeypatch, *labels):
    """The meaning picker, answered the way the operator would."""
    from src.ui.widgets import field_editor

    queue = list(labels)
    monkeypatch.setattr(field_editor.QInputDialog, "getItem",
                        staticmethod(lambda *a, **k: (queue.pop(0), True)))


def test_one_window_adds_places_and_styles_every_text(
        editor_window, monkeypatch) -> None:
    """Everything the office does to a blank happens in this one dialog."""
    from src.ui.widgets.field_editor import FieldEditor

    dialog = FieldEditor(_png(2), [Field(key="fio", page=1)])
    assert dialog._pick_item.count() == 1

    # ➕ a second text on page 1, then drag it, size it, colour it, embolden it
    _answers(monkeypatch, CATALOGUE["pass_full"])
    dialog._add()
    assert dialog._pick_item.count() == 2
    dialog._canvas.move_picked(0.10, 0.20)
    dialog._canvas.resize_picked(1)
    dialog._restyle(bold=True, colour=(0.0, 0.0, 1.0), font="Arial")

    # ➕ one on page 2 — page 1's work is not disturbed by going there
    dialog._pick_page.setCurrentIndex(1)
    _answers(monkeypatch, CATALOGUE["pat_number"])
    dialog._add()

    made = {f.key: f for f in dialog.fields()}
    assert made["pass_full"].bold and made["pass_full"].font == "Arial"
    assert made["pass_full"].colour == (0.0, 0.0, 1.0)
    assert made["pass_full"].x > Field(key="x").x
    assert made["pass_full"].size > Field(key="x").size
    assert made["fio"].page == 1 and made["pat_number"].page == 2
    assert made["fio"].x == Field(key="x").x, "жойидан қимирламаган матн"


def test_deleting_a_text_in_the_window_keeps_the_others(editor_window) -> None:
    from src.ui.widgets.field_editor import FieldEditor

    dialog = FieldEditor(_png(1), [Field(key="fio", page=1),
                                   Field(key="surname", page=1),
                                   Field(key="name", page=1)])
    dialog._pick_item.setCurrentIndex(1)          # «Фамилия»
    dialog._drop()
    assert [f.key for f in dialog.fields()] == ["fio", "name"]
    assert dialog._pick_item.count() == 2
