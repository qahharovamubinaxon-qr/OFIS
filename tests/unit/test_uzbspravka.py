"""УЗБ СПРАВКАЛАР — the office's blanks and its firms' seals.

A worker is placed with one of several firms, and all four of his
certificates carry THAT firm's seal. So the seals are kept by name and
picked by name, and one firm's seal can never turn up on another's paper.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from src.common.errors import ValidationError
from src.config import paths
from src.services import uzbspravka_service as store


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


def _png(tmp_path: Path, name: str) -> Path:
    import fitz

    made = tmp_path / name
    with fitz.open() as doc:
        page = doc.new_page(width=80, height=80)
        page.draw_circle(fitz.Point(40, 40), 30)
        page.get_pixmap(dpi=72).save(str(made))
    return made


def _pdf(tmp_path: Path, name: str) -> Path:
    import fitz

    made = tmp_path / name
    with fitz.open() as doc:
        doc.new_page(width=595, height=842)
        doc.save(str(made))
    return made


# ---------------------------------------------------------------- sheets
def test_the_four_certificates_are_named_the_way_the_office_names_them() -> None:
    assert store.SHEETS == (1, 2, 3, 4)
    assert "хулқ" in store.SHEET_NAMES[1]
    assert "маош" in store.SHEET_NAMES[2]
    assert "мактаб" in store.SHEET_NAMES[3]
    assert "ишлаётган" in store.SHEET_NAMES[4]


def test_each_certificate_keeps_its_own_blank(tmp_path) -> None:
    assert store.blanks() == {}
    store.set_blank(1, _pdf(tmp_path, "one.pdf"))
    store.set_blank(3, _png(tmp_path, "three.png"))
    assert set(store.blanks()) == {1, 3}
    assert store.blank_of(2) is None

    # replacing one leaves the others alone, whatever kind of file it is
    store.set_blank(1, _png(tmp_path, "again.png"))
    assert store.blank_of(1).suffix == ".png"
    assert set(store.blanks()) == {1, 3}
    store.clear_blank(1)
    assert set(store.blanks()) == {3}


def test_a_blank_that_is_not_one_is_refused(tmp_path) -> None:
    good = _pdf(tmp_path, "ok.pdf")
    with pytest.raises(ValidationError, match="1 дан 4"):
        store.set_blank(7, good)
    with pytest.raises(ValidationError, match="PDF ёки расм"):
        store.set_blank(1, tmp_path / "note.txt")
    with pytest.raises(ValidationError, match="топилмади"):
        store.set_blank(1, tmp_path / "missing.pdf")


# ----------------------------------------------------------------- seals
def test_every_firm_keeps_its_own_seal_under_its_own_name(tmp_path) -> None:
    assert store.seals() == {}
    store.add_seal("ООО СФЕРА", _png(tmp_path, "a.png"))
    store.add_seal("ООО ТРАЙД", _png(tmp_path, "b.png"))
    assert set(store.seals()) == {"ООО СФЕРА", "ООО ТРАЙД"}
    assert store.seal_of("ООО СФЕРА") is not None
    assert store.seal_of("ООО ТРАЙД") != store.seal_of("ООО СФЕРА")
    assert store.seal_of("ООО ЙЎҚ") is None
    assert store.seal_of("") is None


def test_uploading_a_firms_seal_again_replaces_it(tmp_path) -> None:
    store.add_seal("ООО СФЕРА", _png(tmp_path, "first.png"))
    first = store.seal_of("ООО СФЕРА")
    store.add_seal("ООО СФЕРА", _png(tmp_path, "second.jpg"))
    assert len(store.seals()) == 1, "битта фирмада иккита печать қолди"
    assert store.seal_of("ООО СФЕРА").suffix == ".jpg"
    assert not first.exists()


def test_a_seal_that_is_not_one_is_refused(tmp_path) -> None:
    with pytest.raises(ValidationError, match="Фирма номи"):
        store.add_seal("   ", _png(tmp_path, "a.png"))
    with pytest.raises(ValidationError, match="расм"):
        store.add_seal("ООО СФЕРА", _pdf(tmp_path, "a.pdf"))
    with pytest.raises(ValidationError, match="топилмади"):
        store.add_seal("ООО СФЕРА", tmp_path / "nope.png")


def test_a_seal_can_be_taken_off_the_list(tmp_path) -> None:
    store.add_seal("ООО СФЕРА", _png(tmp_path, "a.png"))
    store.remove_seal("ООО СФЕРА")
    assert store.seals() == {}
    store.remove_seal("ООО СФЕРА")           # twice is not an error


def test_the_arrangement_is_kept_and_read_back() -> None:
    assert store.load_layout() == {}
    store.save_layout({"fields": {"fio": [0.14, 0.52, 0.012]}})
    assert store.load_layout()["fields"]["fio"] == [0.14, 0.52, 0.012]
