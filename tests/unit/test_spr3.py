"""3-СПРАВКА — the six-page certificate."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.spr3_renderer import (
    Spr3Data,
    output_name,
    render,
    values,
    year_minus_day,
)
from src.pdf.spr3_spec import PAGE_COUNT, PRINTED_PAGES, SLOTS


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _blank(folder: Path, pages: int = PAGE_COUNT) -> Path:
    blank = folder / "SPRAVKA.pdf"
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=595, height=842)
    doc.save(str(blank))
    doc.close()
    return blank


_WORKER = dict(
    surname="ОЙМАХМАДОВ", name="АМИРТЕМИР", patronymic="ХАЙДАРОВИЧ",
    citizenship="ТАДЖИКИСТАН", birth_date=date(1985, 12, 14),
    pass_number="402090755", valid_from=date(2026, 7, 10),
    address="МОСКВА, АЛТУФЬЕВСКОЕ ШОССЕ, Д. 70, К. 1")


def test_the_end_is_a_year_minus_a_day() -> None:
    """The owner's own example: 10.07.2026 → 09.07.2027. Never typed."""
    assert year_minus_day(date(2026, 7, 10)) == date(2027, 7, 9)
    assert year_minus_day(date(2024, 2, 29)) == date(2025, 2, 27)
    assert year_minus_day(None) is None


def test_the_start_date_repeats_on_every_printed_page() -> None:
    made = values(Spr3Data(**_WORKER))
    for page in PRINTED_PAGES:
        assert made[f"p{page}_from"] == "10.07.2026"
        assert made[f"p{page}_to"] == "09.07.2027"
        assert made[f"p{page}_fio"] == "ОЙМАХМАДОВ АМИРТЕМИР ХАЙДАРОВИЧ"
    assert made["p5_address"].startswith("МОСКВА")


def test_every_value_has_a_slot_and_the_other_way_round() -> None:
    made = set(values(Spr3Data(**_WORKER)))
    slotted = set(SLOTS)
    assert made == slotted, (
        f"missing slots: {made - slotted} · dead slots: {slotted - made}")


def test_pages_two_and_four_stay_untouched(tmp_path) -> None:
    """The owner said pages 2 and 4 of the template are empty — and stay so."""
    pdf = render(Spr3Data(**_WORKER), _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        assert doc.page_count == PAGE_COUNT
        for page_no in (2, 4):
            assert not doc[page_no - 1].get_text().strip(), (
                f"page {page_no} was written on")
        for page_no in PRINTED_PAGES:
            ink = doc[page_no - 1].get_text().replace("\xa0", " ")
            assert "ОЙМАХМАДОВ" in ink, f"page {page_no} is empty"
            assert "10.07.2026" in ink and "09.07.2027" in ink
        assert "МОСКВА, АЛТУФЬЕВСКОЕ" in doc[4].get_text().replace("\xa0", " ")


def test_a_short_blank_is_refused(tmp_path) -> None:
    from src.common.errors import OfisError

    with pytest.raises(OfisError):
        render(Spr3Data(**_WORKER), _blank(tmp_path, pages=3))


def test_the_service_stores_and_prints(tmp_path) -> None:
    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.services.spr3_service import Spr3Service

    service = Spr3Service(build_container().resolve(SettingsService))
    blank = service.add_template("СФЕРА", _blank(tmp_path))
    assert blank in service.templates()

    result = service.generate(Spr3Data(**_WORKER), blank)
    assert result.saved.exists()
    assert result.saved.name.startswith("ОЙМАХМАДОВ_АМИРТЕМИР")
    service.remove_template(blank)
    assert blank not in service.templates()


def test_the_filename_is_surname_name() -> None:
    assert output_name(Spr3Data(**_WORKER)) == "ОЙМАХМАДОВ_АМИРТЕМИР.pdf"


def test_the_bot_asks_the_start_date_and_the_address() -> None:
    from src.controllers.ofis_modules import BY_KEY

    module = BY_KEY["spr3"]
    assert module.photo_labels == ("Паспорт", "Русча ФИО ҳужжати")
    fields = [a.field for a in module.asks]
    assert fields == ["valid_from", "address"]
