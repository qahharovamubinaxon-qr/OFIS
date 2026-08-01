"""3-СПРАВКА — the six-page medical certificate, measured off the guide."""

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
    to_latin,
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
        doc.new_page(width=595, height=840)
    doc.save(str(blank))
    doc.close()
    return blank


#: The owner's own guide sample, value for value.
_WORKER = dict(
    surname="ТУРДУБЕК", name="УУЛУ", patronymic="АЙТУРГАН",
    citizenship="КИРГИЗИЯ", birth_date=date(1998, 7, 9), gender="female",
    pass_series="ID", pass_number="1294780",
    pass_issued=date(2019, 7, 8), pass_issued_by="ГРС 212011",
    valid_from=date(2026, 6, 16),
    num3="450215 6510668", ser3="235035", num5="45Г 8889529",
    oblast="Московская область", gorod="г Химки",
    ulitsa="пр-кт Рязанский", dom="72", korpus="2", kvartira="134")


def test_the_end_is_a_year_minus_a_day() -> None:
    assert year_minus_day(date(2026, 6, 16)) == date(2027, 6, 15)
    assert year_minus_day(date(2024, 2, 29)) == date(2025, 2, 27)
    assert year_minus_day(None) is None


def test_every_value_has_a_slot_and_the_other_way_round() -> None:
    made = set(values(Spr3Data(**_WORKER)))
    slotted = set(SLOTS)
    assert made == slotted, (
        f"missing slots: {made - slotted} · dead slots: {slotted - made}")


def test_the_texts_read_exactly_like_the_owners_guide() -> None:
    made = values(Spr3Data(**_WORKER))
    assert made["p1_birth"] == "«09» июля 1998 г"
    assert made["p1_gender"] == "женский"
    assert made["p1_passport"] == ("серия и номер: ID1294780, "
                                   "выдан 08.07.2019 г. ГРС 212011")
    assert made["p1_date_osvid"] == "«16» июня 2026 г"
    assert made["p3_num1"] == "450215" and made["p3_num2"] == "6510668"
    assert made["p3_fio_lat"] == "TURDUBEK UULU AYTURGAN"
    assert made["p3_pass_grajd"] == "ID1294780 КИРГИЗИЯ"
    assert made["p3_date_ser"] == "16.06.2026 сер. 235035"
    assert made["p3_to_day"] == "15" and made["p3_to_year"] == "2027"
    assert made["p5_num1"] == "45Г" and made["p5_num2"] == "8889529"
    assert made["p5_date_yy"] == "26" and made["p5_date_month"] == "июня"
    assert made["p5_passport"] == "ID1294780 выдан 08.07.2019"
    assert made["p5_rf"] == "Российская Федерация"
    assert made["p5_range"] == "с 16.06.2026 до 15.06.2027"
    # the start date on page 6, seven times, two-digit year
    for spot in ("d1", "d2", "d3", "d4", "d5", "d6", "low"):
        assert made[f"p6_{spot}_day"] == "16"
        assert made[f"p6_{spot}_yy"] == "26"


def test_latin_fio_is_transliterated() -> None:
    assert to_latin("ТУРДУБЕК КЫЗЫ") == "TURDUBEK KYZY"


def test_pages_two_and_four_stay_untouched(tmp_path) -> None:
    pdf = render(Spr3Data(**_WORKER), _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        assert doc.page_count == PAGE_COUNT
        for page_no in (2, 4):
            assert not doc[page_no - 1].get_text().strip()
        for page_no in PRINTED_PAGES:
            assert doc[page_no - 1].get_text().strip(), f"page {page_no} empty"
        ink5 = doc[4].get_text().replace("\xa0", " ").replace("\xad", "-")
        assert "пр-кт Рязанский" in ink5
        assert "с 16.06.2026 до 15.06.2027" in ink5


def test_the_values_sit_on_the_measured_spots(tmp_path) -> None:
    pdf = render(Spr3Data(**_WORKER), _blank(tmp_path))
    with fitz.open("pdf", pdf) as doc:
        page = doc[0]
        rect = page.search_for("ТУРДУБЕК УУЛУ АЙТУРГАН")[0]
        assert abs(rect.x0 / page.rect.width - SLOTS["p1_fio"].x) < 0.004
        assert abs(rect.y1 / page.rect.height - SLOTS["p1_fio"].baseline) < 0.02


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
    result = service.generate(Spr3Data(**_WORKER), blank)
    assert result.saved.exists()
    assert result.saved.name.startswith("ТУРДУБЕК_УУЛУ")


def test_the_filename_is_surname_name() -> None:
    assert output_name(Spr3Data(**_WORKER)) == "ТУРДУБЕК_УУЛУ.pdf"


def test_the_bot_asks_the_dates_serials_and_address_pieces() -> None:
    from src.controllers.ofis_modules import BY_KEY

    module = BY_KEY["spr3"]
    fields = [a.field for a in module.asks]
    assert fields[0] == "valid_from"
    for wanted in ("num3", "ser3", "num5", "oblast", "gorod", "ulitsa",
                   "dom", "korpus", "kvartira"):
        assert wanted in fields
