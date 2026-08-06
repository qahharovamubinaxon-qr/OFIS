"""МЕД КНИЖКА — the four pages the office prints for the commission.

Every expected place here was measured off the office's own pages: they
were split by colour — blue for the dates, red for the book number, grey
for the typed block — and each mark was boxed. The tests hold the program
to those places and to the office's own way of writing a date.
"""

from __future__ import annotations

import tempfile
from datetime import date

import fitz
import pytest
from src.common.errors import ValidationError
from src.config import paths
from src.pdf.medkniga_renderer import (
    MedKnigaData,
    a_year_on,
    dotted_date,
    render,
    stamp_date,
)
from src.pdf.medkniga_spec import (
    ALL_SLOTS,
    BLUE,
    EXAM_KEYS,
    NUMBER_KEYS,
    PAGE_H,
    PAGE_W,
    PAGES,
    RED,
)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _data(**over) -> MedKnigaData:
    made = MedKnigaData(
        surname="Расулов", name="Азиз", patronymic="Расулжон Угли",
        birth_year="1992", city="Москва", position="ПОМОЩНИК ПОВАРА",
        number="8832888", exam_date=date(2026, 8, 5))
    for key, value in over.items():
        setattr(made, key, value)
    return made


def _spans(pdf: bytes) -> list[dict]:
    found = []
    with fitz.open("pdf", pdf) as doc:
        for number, page in enumerate(doc, start=1):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        span["text"] = " ".join(span["text"].split())
                        span["page"] = number
                        found.append(span)
    return found


# ----------------------------------------------------------------- dates
def test_the_date_reads_the_way_the_booklet_stamps_it() -> None:
    """«05 АВГ 2026» — the three letters, never «08» and never «августа»."""
    assert stamp_date(date(2026, 8, 5)) == "05 АВГ 2026"
    assert stamp_date(date(2027, 1, 31)) == "31 ЯНВ 2027"
    assert stamp_date(date(2026, 12, 9)) == "09 ДЕК 2026"
    assert stamp_date(None) == ""
    assert dotted_date(date(2026, 8, 5)) == "05. 08. 2026"


def test_a_book_lasts_exactly_one_year() -> None:
    assert a_year_on(date(2026, 8, 5)) == date(2027, 8, 5)
    # a leap day has no anniversary — it falls back to the 28th
    assert a_year_on(date(2028, 2, 29)) == date(2029, 2, 28)
    assert a_year_on(None) is None
    assert _data().expires() == date(2027, 8, 5)


# ----------------------------------------------------------------- pages
def test_four_pages_come_out_at_the_office_s_own_size() -> None:
    with fitz.open("pdf", render(_data())) as doc:
        assert doc.page_count == PAGES
        for page in doc:
            assert page.rect.width == pytest.approx(PAGE_W)
            assert page.rect.height == pytest.approx(PAGE_H)


def test_the_worker_lands_where_the_office_writes_him() -> None:
    spans = _spans(render(_data()))
    where = {s["text"]: (s["origin"][0] / PAGE_W, s["origin"][1] / PAGE_H)
             for s in spans}
    assert where["Расулов"] == pytest.approx((0.3556, 0.5844), abs=0.004)
    assert where["Азиз Расулжон Угли"] == pytest.approx((0.3538, 0.6084),
                                                        abs=0.004)
    assert where["1992"] == pytest.approx((0.3556, 0.6346), abs=0.004)
    assert where["Москва"] == pytest.approx((0.3542, 0.6607), abs=0.004)
    # a trade is one thing, not two names
    assert "Помощник повара" in where


def test_the_number_and_the_date_repeat_on_every_page_that_carries_them() -> None:
    """The office asked for one number and one date, written once."""
    spans = _spans(render(_data()))
    numbers = [s for s in spans if s["text"] == "8832888"]
    assert {s["page"] for s in numbers} == {1, 3, 4}, "рақам ҳар бетда эмас"
    stamped = [s for s in spans if s["text"] == "05 АВГ 2026"]
    # once on page 1, once on page 3, and one per doctor's line on page 4
    assert len([s for s in stamped if s["page"] == 4]) == 13
    assert {s["page"] for s in stamped} == {1, 3, 4}
    assert len(stamped) == len(EXAM_KEYS)


def test_the_training_page_carries_both_ends_of_the_year() -> None:
    spans = {s["text"] for s in _spans(render(_data())) if s["page"] == 2}
    assert "05. 08. 2026" in spans
    assert "05. 08. 2027" in spans
    assert "помощник повара" in spans, "қўлёзма лавозим ёзилмади"


def test_the_inks_are_the_office_s_own() -> None:
    """Blue for the dates, red for the number — read off its own pages."""
    for key in NUMBER_KEYS:
        assert ALL_SLOTS[key].colour == RED, key
    for key in EXAM_KEYS:
        assert ALL_SLOTS[key].colour == BLUE, key


def test_nothing_is_written_for_a_worker_who_has_no_number() -> None:
    spans = {s["text"] for s in _spans(render(_data(number="")))}
    assert "№" not in spans and "8832888" not in spans


def test_every_slot_has_a_label_and_a_sample() -> None:
    for key, slot in ALL_SLOTS.items():
        assert slot.label, key
        assert slot.sample, key
        assert 1 <= slot.page <= PAGES, key


# --------------------------------------------------------------- service
def test_it_refuses_what_it_cannot_print(tmp_path) -> None:
    from src.services.medkniga_service import MedKnigaService

    service = MedKnigaService()
    with pytest.raises(ValidationError, match="Фамилия"):
        service.generate(_data(surname=""), output_dir=tmp_path)
    with pytest.raises(ValidationError, match="сана"):
        service.generate(_data(exam_date=None), output_dir=tmp_path)
    with pytest.raises(ValidationError, match="рақам"):
        service.generate(_data(number=""), output_dir=tmp_path)


def test_the_next_worker_starts_one_number_along(tmp_path) -> None:
    """The office reads the number off the booklet in its hand; the program
    only offers the next one so it is not typed twice."""
    from src.services.medkniga_service import (
        MedKnigaService,
        next_number,
        remember_number,
    )

    assert next_number() == ""
    result = MedKnigaService().generate(_data(), output_dir=tmp_path)
    assert result.pdf_path.name == "РАСУЛОВ_АЗИЗ.pdf"
    assert result.expires == date(2027, 8, 5)
    assert next_number() == "8832889"
    # the leading zeros of a series are kept
    remember_number("0000123")
    assert next_number() == "0000124"
    # a number with letters is the office's own business, left alone
    remember_number("ПР-77")
    assert next_number() == "ПР-77"


def test_a_blank_is_optional_and_replaceable(tmp_path) -> None:
    """Blank pages print on white; an uploaded scan goes UNDER the marks."""
    from src.services.medkniga_service import blank_of, blanks, set_blank

    assert blanks() == {}
    scan = tmp_path / "page1.pdf"
    with fitz.open() as doc:
        doc.new_page(width=PAGE_W, height=PAGE_H)
        doc.save(str(scan))
    set_blank(1, scan)
    assert blank_of(1) is not None and blanks().keys() == {1}
    with pytest.raises(ValidationError):
        set_blank(9, scan)
    with pytest.raises(ValidationError):
        set_blank(1, tmp_path / "nope.txt")


def test_a_dragged_mark_really_moves(tmp_path) -> None:
    from src.services.medkniga_service import MedKnigaService, save_layout

    save_layout({"fields": {"surname": [0.20, 0.30, 0.02]}})
    result = MedKnigaService().generate(_data(), output_dir=tmp_path)
    span = next(s for s in _spans(result.pdf_path.read_bytes())
                if s["text"] == "Расулов")
    assert span["origin"][0] / PAGE_W == pytest.approx(0.20, abs=0.01)
    assert span["origin"][1] / PAGE_H == pytest.approx(0.30, abs=0.01)


def test_the_data_comes_off_whichever_document_was_dropped() -> None:
    from types import SimpleNamespace

    from src.services.medkniga_service import data_of

    passport = SimpleNamespace(surname="КАХОРОВ", name="АББОСБЕК",
                               patronymic="ЖУРАМУРОД УГЛИ",
                               birth_date=date(1995, 1, 13))
    made = data_of(passport, None, position="Повар", city="Москва",
                   number="1", exam_date=date(2026, 8, 5))
    assert made.surname == "КАХОРОВ" and made.birth_year == "1995"
    assert made.given_names() == "АББОСБЕК ЖУРАМУРОД УГЛИ"
    # with only a patent, its own ФИО is used
    patent = SimpleNamespace(holder_surname="КАХОРОВ", holder_name="АББОСБЕК",
                             holder_patronymic=None)
    made = data_of(None, patent, position="Повар", city="Москва", number="1",
                   exam_date=date(2026, 8, 5))
    assert made.surname == "КАХОРОВ" and made.birth_year == ""


def test_the_section_is_on_the_phone_too() -> None:
    from src.controllers.ofis_modules import BY_KEY

    assert "medkniga" in BY_KEY
    assert BY_KEY["medkniga"].asks, "бот сўровлари йўқ"


def test_no_registry_or_verification_artefact_is_produced() -> None:
    """The office asked for a «подтверждение» page imitating the state ЛМК
    register, hosted and linked by a QR on the booklet. It is not built,
    and nothing in the section may quietly grow into one."""
    import inspect

    from src.pdf import medkniga_renderer, medkniga_spec
    from src.services import medkniga_service

    for module in (medkniga_spec, medkniga_renderer, medkniga_service):
        source = inspect.getsource(module).lower()
        for forbidden in ("реестр", "imgbb", "qrcode", "подтвержд"):
            assert forbidden not in source, f"{module.__name__}: {forbidden}"
