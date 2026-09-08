from datetime import date

import fitz
import pytest
from src.common.errors import ValidationError
from src.pdf.alliance_renderer import AllianceData
from src.services.alliance_service import SLOTS, AllianceService


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    from src.config import paths
    paths.data_dir.cache_clear()
    yield tmp_path
    paths.data_dir.cache_clear()


def _pdf(tmp_path, name, pages=1):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=842, height=632)
    p = tmp_path / name
    doc.save(str(p))
    doc.close()
    return p


def test_generate_needs_all_three_blanks(appdata, tmp_path):
    svc = AllianceService()
    svc.set_blank("udo", _pdf(tmp_path, "u.pdf", 2))
    data = AllianceData(surname="АШУРОВ", name="ДИЛМУРОД",
                        start_date=date(2026, 9, 7))
    with pytest.raises(ValidationError):
        svc.generate(data)


def test_generate_needs_a_surname(appdata, tmp_path):
    svc = AllianceService()
    svc.set_blank("udo", _pdf(tmp_path, "u.pdf", 2))
    svc.set_blank("spr1", _pdf(tmp_path, "s1.pdf"))
    svc.set_blank("spr2", _pdf(tmp_path, "s2.pdf"))
    with pytest.raises(ValidationError):
        svc.generate(AllianceData(surname="", start_date=date(2026, 9, 7)))


def test_generate_makes_three_named_pdfs(appdata, tmp_path):
    svc = AllianceService()
    svc.set_blank("udo", _pdf(tmp_path, "u.pdf", 2))
    svc.set_blank("spr1", _pdf(tmp_path, "s1.pdf"))
    svc.set_blank("spr2", _pdf(tmp_path, "s2.pdf"))
    data = AllianceData(surname="АШУРОВ", name="ДИЛМУРОД",
                        start_date=date(2026, 9, 7))
    out = svc.generate(data)
    assert {r.slot for r in out} == set(SLOTS)
    names = {r.saved.name for r in out}
    assert names == {"АШУРОВ_ДИЛМУРОД_УДОСТОВЕРЕНИЕ.pdf",
                     "АШУРОВ_ДИЛМУРОД_СПРАВКА_1.pdf",
                     "АШУРОВ_ДИЛМУРОД_СПРАВКА_2.pdf"}
    for r in out:
        assert r.saved.exists()
        assert r.pdf[:4] == b"%PDF"


def test_generate_into_a_chosen_folder(appdata, tmp_path):
    svc = AllianceService()
    svc.set_blank("udo", _pdf(tmp_path, "u.pdf", 2))
    svc.set_blank("spr1", _pdf(tmp_path, "s1.pdf"))
    svc.set_blank("spr2", _pdf(tmp_path, "s2.pdf"))
    where = tmp_path / "chosen"
    out = svc.generate(AllianceData(surname="АШУРОВ", name="ДИЛМУРОД",
                                    start_date=date(2026, 9, 7)), out_dir=where)
    for r in out:
        assert r.saved.parent == where


def test_pages_and_layout_roundtrip(appdata, tmp_path):
    svc = AllianceService()
    svc.set_blank("udo", _pdf(tmp_path, "u.pdf", 2))
    assert svc.pages("udo") == 2
    assert svc.pages("spr1") == 0
    svc.save_layout("udo", {"fields": [{"key": "surname", "page": 1}]})
    assert svc.layout("udo").get("fields")
