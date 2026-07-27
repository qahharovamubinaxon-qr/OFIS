"""УМУМИЙ template store: save a document once, fill it for any worker."""

from __future__ import annotations

import json
import tempfile
from datetime import date

import fitz
import pytest

from src.config import paths
from src.domain.documents import Passport, Patent
from src.domain.enums import Gender


@pytest.fixture(autouse=True)
def _appdata(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _passport(surname="ИСАКОВ", name="ШАХБОЗ") -> Passport:
    return Passport(
        surname=surname, name=name, patronymic="АКМАЛЖОН УГЛИ",
        nationality="УЗБЕКИСТАН", birth_date=date(2000, 12, 27), gender=Gender.MALE,
        number="FA7822242", issue_date=date(2021, 3, 10),
        expiry_date=date(2031, 3, 9))


def _patent() -> Patent:
    return Patent(series="77", number="2600077440",
                  issue_date=date(2026, 1, 15), profession="ЭЛЕКТРОГАЗОСВАРЩИК")


def _contract(tmp_path, worker="РАХИМОВ БАДРИДДИН"):
    """A small text PDF that carries a previous worker's details."""
    from src.pdf.engine import _font_file

    pdf = tmp_path / "dogovor.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # a Cyrillic-capable font, like the office's real documents use
    page.insert_font(fontname="t", fontfile=str(_font_file("OfisSerif")))
    for y, line in ((100, "ООО СЕРВИСБЫТ, ИНН 7733481040"),
                    (130, f"Работник: {worker}"),
                    (160, "Гражданство: ТАДЖИКИСТАН")):
        page.insert_text((70, y), line, fontname="t", fontsize=11)
    doc.save(str(pdf))
    doc.close()
    return pdf


_FOUND = [
    {"line": 1, "text": "РАХИМОВ БАДРИДДИН", "field": "fio_full"},
    {"line": 2, "text": "ТАДЖИКИСТАН", "field": "citizenship"},
]


@pytest.fixture()
def svc(monkeypatch):
    from src.services.umumiy_templates import UmumiyTemplateService

    monkeypatch.setattr("src.services.umumiy_templates.ask",
                        lambda *a, **k: json.dumps(_FOUND))
    return UmumiyTemplateService(key_getter=lambda: "test-key")


# ---------------------------------------------------------------- create


def test_template_blanks_the_previous_worker_and_remembers_the_spots(svc, tmp_path):
    tpl = svc.create(_contract(tmp_path), "Договор СЕРВИСБЫТ")

    assert tpl.name == "Договор СЕРВИСБЫТ"
    assert tpl.fields == 2 and not tpl.scanned

    text = "".join(p.get_text() for p in fitz.open(tpl.pdf_path))
    assert "РАХИМОВ" not in text, "the old worker's name is still in the template"
    assert "ТАДЖИКИСТАН" not in text
    # the company's own details survive untouched
    assert "7733481040" in text and "СЕРВИСБЫТ" in text


def test_saved_template_is_listed_and_deletable(svc, tmp_path):
    tpl = svc.create(_contract(tmp_path), "Договор")
    assert [t.slug for t in svc.list()] == [tpl.slug]
    assert svc.get(tpl.slug) is not None

    svc.delete(tpl.slug)
    assert svc.list() == []
    assert svc.get(tpl.slug) is None


def test_same_name_twice_gets_its_own_slot(svc, tmp_path):
    a = svc.create(_contract(tmp_path), "Договор")
    b = svc.create(_contract(tmp_path), "Договор")
    assert a.slug != b.slug
    assert len(svc.list()) == 2


def test_company_requisites_are_never_blanked(monkeypatch, tmp_path):
    """Even if the model points at the company's ИНН, it is refused."""
    from src.services.umumiy_templates import UmumiyTemplateService

    monkeypatch.setattr("src.services.umumiy_templates.ask", lambda *a, **k: json.dumps(
        [{"line": 0, "text": "ИНН 7733481040", "field": "passport_number"},
         {"line": 1, "text": "РАХИМОВ БАДРИДДИН", "field": "fio_full"}]))
    svc2 = UmumiyTemplateService(key_getter=lambda: "k")
    tpl = svc2.create(_contract(tmp_path), "Договор")

    assert tpl.fields == 1, "the ИНН fragment must be dropped"
    assert "7733481040" in "".join(p.get_text() for p in fitz.open(tpl.pdf_path))


def test_a_document_with_no_worker_data_is_refused(monkeypatch, tmp_path):
    from src.common.errors import OfisError
    from src.services.umumiy_templates import UmumiyTemplateService

    monkeypatch.setattr("src.services.umumiy_templates.ask", lambda *a, **k: "[]")
    with pytest.raises(OfisError) as exc:
        UmumiyTemplateService(key_getter=lambda: "k").create(
            _contract(tmp_path), "Бўш")
    assert "topilmadi" in exc.value.message.lower()


# ------------------------------------------------------------------ fill


def test_filling_uses_no_ai_and_writes_the_new_worker(svc, tmp_path, monkeypatch):
    tpl = svc.create(_contract(tmp_path), "Договор")

    # once saved, filling must never call the model again
    def explode(*a, **k):
        raise AssertionError("fill() must not call the AI")

    monkeypatch.setattr("src.services.umumiy_templates.ask", explode)

    out = svc.fill(tpl.slug, _passport(), _patent(), form_date=date(2026, 7, 26))
    text = "".join(p.get_text() for p in fitz.open(out))
    assert "ИСАКОВ" in text
    assert "УЗБЕКИСТАН" in text
    assert "РАХИМОВ" not in text and "ТАДЖИКИСТАН" not in text


def test_the_same_template_serves_a_second_worker(svc, tmp_path):
    tpl = svc.create(_contract(tmp_path), "Договор")
    first = svc.fill(tpl.slug, _passport(), None, form_date=date(2026, 7, 26))
    second = svc.fill(tpl.slug, _passport("КОБУЛОВ", "ШЕРАЛИ"), None,
                      form_date=date(2026, 7, 26))

    assert first != second, "each run gets its own file"
    assert "ИСАКОВ" in "".join(p.get_text() for p in fitz.open(first))
    assert "КОБУЛОВ" in "".join(p.get_text() for p in fitz.open(second))


def test_casing_follows_the_original_document(svc, tmp_path):
    """The old text was upper case, so the new value is written upper case."""
    tpl = svc.create(_contract(tmp_path), "Договор")
    fields = json.loads(
        (tpl.pdf_path.parent / "fields.v1.json").read_text(encoding="utf-8"))
    assert {f["case"] for f in fields["fields"]} == {"upper"}

    out = svc.fill(tpl.slug, _passport(), None, form_date=date(2026, 7, 26))
    assert "ИСАКОВ" in "".join(p.get_text() for p in fitz.open(out))


def test_filling_a_missing_template_is_reported(svc):
    from src.common.errors import OfisError

    with pytest.raises(OfisError):
        svc.fill("yoq", _passport(), None, form_date=date(2026, 7, 26))


# ------------------------------------------------------------ scans


def test_a_scan_is_studied_from_page_images(monkeypatch, tmp_path):
    from src.services.umumiy_templates import UmumiyTemplateService

    scan = tmp_path / "scan.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)   # no text layer at all
    doc.save(str(scan))
    doc.close()

    monkeypatch.setattr("src.services.umumiy_templates.ask", lambda *a, **k: json.dumps(
        [{"page": 0, "text": "РАХИМОВ БАДРИДДИН", "field": "fio_full",
          "box": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.23}}]))

    svc2 = UmumiyTemplateService(key_getter=lambda: "k")
    tpl = svc2.create(scan, "Скан договор")
    assert tpl.scanned and tpl.fields == 1

    out = svc2.fill(tpl.slug, _passport(), None, form_date=date(2026, 7, 26))
    assert "ИСАКОВ" in "".join(p.get_text() for p in fitz.open(out))


def test_field_values_cover_the_whole_vocabulary():
    from src.services.umumiy_fields import FIELD_KEYS, field_value

    resolved = {k: field_value(k, _passport(), _patent(), date(2026, 7, 26))
                for k in FIELD_KEYS}
    assert resolved["fio_full"] == "ИСАКОВ ШАХБОЗ АКМАЛЖОН УГЛИ"
    assert resolved["fio_short"] == "ИСАКОВ Ш.А."
    assert resolved["birth_date"] == "27.12.2000"
    assert resolved["passport_full"] == "FA7822242"
    assert resolved["patent_full"] == "772600077440"
    assert resolved["form_date"] == "26.07.2026"
    # everything the fixture actually carries resolves; the two it omits
    # (паспорт серия, кем выдан) come back empty rather than raising
    missing = {k for k, v in resolved.items() if not v}
    assert missing == {"passport_series", "passport_issued_by"}


def test_unknown_field_key_resolves_to_empty():
    from src.services.umumiy_fields import field_value

    assert field_value("boshqa", _passport(), None, date(2026, 7, 26)) == ""


def test_patent_fields_are_empty_without_a_patent():
    from src.services.umumiy_fields import field_value

    assert field_value("patent_full", _passport(), None, date(2026, 7, 26)) == ""
