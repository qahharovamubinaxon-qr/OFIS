"""The УЗБ СПРАВКАЛАР screen — what the office sees and what it may press.

Two things this screen must get right, because both were asked for in so many
words: what is PRINTED is what is in the boxes (the reader only fills them in,
the office has the last word), and the firm is picked from the firms whose
seals are actually uploaded — a certificate cannot go out under a seal that
does not exist.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.uzbspravka_renderer import UzbData
from src.services import uzbspravka_service as store


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    sandbox = tempfile.mkdtemp()
    monkeypatch.setenv("XDG_DATA_HOME", sandbox)
    monkeypatch.setenv("LOCALAPPDATA", sandbox)
    paths.data_dir.cache_clear()
    yield
    paths.data_dir.cache_clear()


class _Controller:
    """The bridge, standing still — the screen is what is under test."""

    def __init__(self, read: UzbData | None = None) -> None:
        self.read = read or UzbData()
        self.printed: list[tuple] = []

    def ai_available(self) -> bool:
        return True

    def can_make_qr(self) -> bool:
        return True

    def sheets(self):
        return store.SHEETS

    def sheet_names(self):
        return dict(store.SHEET_NAMES)

    def sheet_short(self):
        return dict(store.SHEET_SHORT)

    def blanks(self):
        return store.blanks()

    def seals(self):
        return store.seals()

    def layout(self):
        return {}

    def new_numbers(self, sheets=store.SHEETS):
        return store.new_numbers(sheets)

    def read_passport(self, image, *, firm):
        return self.read

    def generate(self, data, sheets, *, numbers=None, with_qr=True):
        self.printed.append((data, sheets, numbers, with_qr))
        raise AssertionError("бу тест чоп этишни кутмайди")


def _seal(tmp_path: Path, firm: str) -> None:
    made = tmp_path / f"{firm}.png"
    with fitz.open() as doc:
        page = doc.new_page(width=60, height=60)
        page.draw_circle(fitz.Point(30, 30), 22)
        page.get_pixmap(dpi=72).save(str(made))
    store.add_seal(firm, made)


@pytest.fixture()
def screen():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    def build(controller):
        from src.ui.views.uzbspravka_view import UzbSpravkaView

        return UzbSpravkaView(controller)

    yield build, app


# ------------------------------------------------------------- the firms
def test_only_firms_with_a_seal_can_be_chosen(screen, tmp_path) -> None:
    _seal(tmp_path, "ООО СФЕРА")
    _seal(tmp_path, "ООО ТРАЙД")
    build, _app = screen
    view = build(_Controller())
    shown = [view._firm.itemText(i) for i in range(view._firm.count())]
    assert shown == ["ООО СФЕРА", "ООО ТРАЙД"]
    view.deleteLater()


def test_without_a_firm_nothing_is_printed(screen) -> None:
    build, _app = screen
    view = build(_Controller())
    view._surname.setText("ЭРГАШЕВ")
    view._generate()
    assert "Фирма" in view._status.text()
    view.deleteLater()


def test_without_a_name_nothing_is_printed(screen, tmp_path) -> None:
    _seal(tmp_path, "ООО СФЕРА")
    build, _app = screen
    view = build(_Controller())
    view._generate()
    assert "Фамилия" in view._status.text()
    view.deleteLater()


def test_with_no_certificate_ticked_nothing_is_printed(screen,
                                                       tmp_path) -> None:
    _seal(tmp_path, "ООО СФЕРА")
    build, _app = screen
    view = build(_Controller())
    view._surname.setText("ЭРГАШЕВ")
    for tick in view._ticks.values():
        tick.setChecked(False)
    view._generate()
    assert "битта справкани" in view._status.text()
    view.deleteLater()


# ---------------------------------------------------------- what is read
def test_the_reading_fills_the_boxes(screen) -> None:
    build, _app = screen
    view = build(_Controller())
    view._filled(UzbData(
        surname="ЭРГАШЕВ", name="УМИДЖОН", patronymic="ШУХРАТ УГЛИ",
        latin_name="ERGASHEV UMIDJON SHUKHRAT UGLI", passport="FA3445084",
        pinfl="50210025720042", birth_date=date(2002, 10, 2)))
    assert view._surname.text() == "ЭРГАШЕВ"
    assert view._pinfl.text() == "50210025720042"
    assert view._born.date().toPython() == date(2002, 10, 2)
    assert "✅" in view._status.text()
    view.deleteLater()


def test_an_unread_pinfl_is_said_out_loud(screen) -> None:
    """The strip is the only place it is printed — a blurred one must not
    pass in silence, because the box would go out empty."""
    build, _app = screen
    view = build(_Controller())
    view._filled(UzbData(surname="ЭРГАШЕВ", pinfl=""))
    assert "ПИНФЛ" in view._status.text() and "⚠️" in view._status.text()
    view.deleteLater()


def test_what_is_printed_is_what_is_in_the_boxes(screen) -> None:
    """«Always show editable form» — the office's typing outranks the reader."""
    build, _app = screen
    view = build(_Controller())
    view._filled(UzbData(surname="ЭРГАШЕВ", pinfl="50210025720042"))
    view._pinfl.setText("31301954050087")           # corrected by hand
    view._surname.setText("КАХОРОВ")
    made = view._data()
    assert made.pinfl == "31301954050087"
    assert made.surname == "КАХОРОВ"
    view.deleteLater()


# --------------------------------------------------------- the QR switch
def test_the_qr_box_is_off_and_locked_without_the_keys(screen) -> None:
    class _NoKeys(_Controller):
        def can_make_qr(self) -> bool:
            return False

    build, _app = screen
    view = build(_NoKeys())
    assert view._qr.isChecked() is False
    assert view._qr.isEnabled() is False
    view.deleteLater()


# ------------------------------------------------------------ the numbers
def test_each_worker_starts_with_his_own_numbers(screen) -> None:
    build, _app = screen
    view = build(_Controller())
    assert sorted(view._numbers) == [1, 2, 3, 4]
    codes = {n.code for n in view._numbers.values()}
    assert len(codes) == 4 and all(len(c) == 4 for c in codes)
    view.deleteLater()


# ----------------------------------------------------------- the arranger
def test_every_sheet_goes_into_the_editor_wearing_its_own_number() -> None:
    """1, 2 and 3 hold the same names, and the editor knows a text by its key
    alone — without the sheet in front, dragging one would drag three."""
    from src.pdf.uzbspravka_spec import SEAL_KEY
    from src.ui.views.uzbspravka_view import to_fields

    catalogue, samples, fields = to_fields(store.SHEETS, {})
    keys = [f.key for f in fields]
    assert "1:pinfl" in keys and "4:pinfl" in keys
    assert len(keys) == len(set(keys)), "иккита матн битта калит билан келди"
    assert all(f.page in store.SHEETS for f in fields)
    assert f"2:{SEAL_KEY}" in keys and "3:img_qr" in keys
    assert catalogue["4:surname"].startswith("4-справка")
    assert samples["1:pinfl"]


def test_what_the_editor_leaves_is_what_the_renderer_reads_back() -> None:
    from dataclasses import replace

    from src.pdf.uzbspravka_renderer import placed, placed_images
    from src.pdf.uzbspravka_spec import SEAL_KEY
    from src.ui.views.uzbspravka_view import to_fields, to_layout

    _cat, samples, fields = to_fields(store.SHEETS, {})
    dragged = {"4:pinfl": (0.44, 0.62, 0.014),
               f"1:{SEAL_KEY}": (0.10, 0.30, 0.05)}
    moved = [replace(f, x=dragged[f.key][0], baseline=dragged[f.key][1],
                     size=dragged[f.key][2]) if f.key in dragged else f
             for f in fields]

    layout = to_layout(moved, samples)
    assert placed(4, layout)["pinfl"].x == pytest.approx(0.44)
    assert placed(1, layout)["pinfl"].x != pytest.approx(0.44)
    assert placed_images(1, layout)[SEAL_KEY] == (0.10, 0.30, 0.05)
    assert placed_images(2, layout)[SEAL_KEY] != (0.10, 0.30, 0.05)


def test_the_next_worker_does_not_inherit_the_last_ones_codes(
        screen, tmp_path, monkeypatch) -> None:
    build, _app = screen
    view = build(_Controller())
    before = {s: n.code for s, n in view._numbers.items()}

    class _Done:
        pdfs = {1: tmp_path / "a.pdf"}
        codes = {1: before[1]}
        firm = "ООО СФЕРА"

    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4\n")
    from src.ui.widgets import save_to

    monkeypatch.setattr(save_to, "ask_save_dir", lambda *a, **k: None)
    view._done(_Done())
    assert {s: n.code for s, n in view._numbers.items()} != before
    view.deleteLater()
