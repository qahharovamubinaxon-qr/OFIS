"""ЧЕК — a blank the office uploads stays until the office deletes it.

In the office's own words: «ЧЕК бўлимига шаблон юкласам ҳар update
қилганимда учиб кетяпти, қайтадан улаяпман». It was being copied in beside
the blanks that ship with the program, and rebuilding the EXE replaces that
folder wholesale — so every update swept the office's blank away with it.

AppData is the one place a rebuild cannot reach.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.controllers import chek_controller
from src.controllers.chek_controller import ChekController


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    # the program's own folder, standing in for the one a rebuild replaces
    shipped = tmp_path / "program" / "templates" / "chek"
    shipped.mkdir(parents=True)
    monkeypatch.setattr(chek_controller, "SHIPPED_DIR", shipped)
    yield shipped
    paths.data_dir.cache_clear()


def _pdf(folder: Path, name: str) -> Path:
    made = folder / name
    made.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as doc:
        doc.new_page(width=227, height=1583)
        doc.save(str(made))
    return made


def _controller() -> ChekController:
    return ChekController(ocr=None)


def test_an_uploaded_blank_is_kept_outside_the_program_folder(
        tmp_path, isolated) -> None:
    control = _controller()
    added = control.add_template(_pdf(tmp_path, "офис бланкаси.pdf"))
    assert added.exists()
    assert added.parent == chek_controller.user_dir()
    assert str(paths.user_templates_dir()) in str(added)
    assert not (isolated / added.name).exists(), "программа папкасига тушди"


def test_it_is_still_there_after_the_program_folder_is_replaced(
        tmp_path, isolated) -> None:
    """This is the update: the shipped folder is thrown away and rebuilt."""
    control = _controller()
    _pdf(isolated, "premiya_blank.pdf")               # what ships with it
    mine = control.add_template(_pdf(tmp_path, "меники.pdf"))

    for old in isolated.glob("*.pdf"):                # the rebuild
        old.unlink()
    _pdf(isolated, "premiya_blank.pdf")

    names = [p.name for p in control.templates()]
    assert "меники.pdf" in names, "update дан кейин шаблон учиб кетди"
    assert mine.exists()


def test_a_blank_left_in_the_program_folder_is_carried_to_safety(
        isolated) -> None:
    """Whatever the office uploaded BEFORE this change is rescued once."""
    _pdf(isolated, "эски юклаган.pdf")
    control = _controller()
    assert "эски юклаган.pdf" in [p.name for p in control.templates()]
    assert (chek_controller.user_dir() / "эски юклаган.pdf").exists()


def test_only_the_office_takes_a_blank_off_the_list(tmp_path, isolated) -> None:
    control = _controller()
    mine = control.add_template(_pdf(tmp_path, "меники.pdf"))
    control.remove_template(mine)
    assert not mine.exists()
    assert "меники.pdf" not in [p.name for p in control.templates()]


def test_a_shipped_blank_is_never_deleted(isolated) -> None:
    """Deleting it would only bring it back with the next rebuild."""
    shipped = _pdf(isolated, "premiya_blank.pdf")
    control = _controller()
    control.templates()                               # rescues a copy
    control.remove_template(shipped)
    assert shipped.exists()


def test_the_offices_own_blank_outranks_a_shipped_one_of_the_same_name(
        tmp_path, isolated) -> None:
    """It replaced it on purpose — the replacement is what prints."""
    _pdf(isolated, "premiya_blank.pdf")
    control = _controller()
    control.templates()
    mine = chek_controller.user_dir() / "premiya_blank.pdf"
    mine.write_bytes(_pdf(tmp_path, "other.pdf").read_bytes())
    chosen = [p for p in control.templates() if p.name == "premiya_blank.pdf"]
    assert chosen == [mine]
