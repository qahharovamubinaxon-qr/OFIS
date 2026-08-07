"""КУК ПАТЕНТ — the screen, and what the office may press on it.

Three things the office asked for by name and this holds to: what is PRINTED
is what is in the boxes, a firm typed once comes back in the list, and the
card's own number is offered already moved on so a run of workers needs no
typing after the first.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import fitz
import pytest
from src.config import paths
from src.pdf.kukpatent_renderer import KukPatentData
from src.pdf.kukpatent_spec import BACK, FRONT, PHOTO_KEY
from src.services import kukpatent_service as store


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

    def __init__(self, read: KukPatentData | None = None) -> None:
        self.read = read or KukPatentData()

    def ai_available(self) -> bool:
        return True

    def sides(self):
        return store.SIDES

    def side_names(self):
        return dict(store.SIDE_NAMES)

    def blanks(self):
        return store.blanks()

    def firms(self):
        return store.firms()

    def forget_firm(self, firm):
        store.forget_firm(firm)

    def next_number(self):
        return store.next_number()

    def typed(self):
        return store.typed()

    def remember_typed(self, **boxes):
        store.remember_typed(**boxes)

    def layout(self):
        return store.load_layout()

    def save_layout(self, layout):
        store.save_layout(layout)

    def read_passport(self, image, **kw):
        return self.read


@pytest.fixture()
def screen():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    def build(controller=None):
        from src.ui.views.kukpatent_view import KukPatentView

        return KukPatentView(controller or _Controller())

    yield build, app


def _pdf(tmp_path: Path, name: str) -> Path:
    made = tmp_path / name
    with fitz.open() as doc:
        doc.new_page(width=595.2, height=411.1)
        doc.save(str(made))
    return made


# ------------------------------------------------------------- the firms
def test_a_firm_typed_once_comes_back_in_the_list(screen) -> None:
    store.remember_firm("ООО САТУРН")
    build, _app = screen
    view = build()
    shown = [view._firm.itemText(i) for i in range(view._firm.count())]
    assert shown == ["ООО САТУРН"]
    view.deleteLater()


def test_a_firm_broken_across_two_lines_is_kept_whole(screen) -> None:
    """A combo box makes a mess of a newline — the break is hidden in the
    list and handed back whole when that firm is picked."""
    store.remember_firm('ООО "Сфера"\nотдел кадров')
    build, _app = screen
    view = build()
    assert view._firm.itemText(0) == 'ООО "Сфера" отдел кадров'
    view._firm.setCurrentIndex(0)
    assert view._firm_text() == 'ООО "Сфера"\nотдел кадров'
    view.deleteLater()


def test_the_office_may_break_the_firm_itself(screen) -> None:
    build, _app = screen
    view = build()
    view._firm.setCurrentText("ООО САТУРН")
    view._firm2.setPlainText("ООО САТУРН\nотдел кадров")
    assert view._firm_text() == "ООО САТУРН\nотдел кадров"
    view.deleteLater()


def test_without_a_firm_nothing_is_printed(screen) -> None:
    build, _app = screen
    view = build()
    view._surname.setText("Эргешов")
    view._generate()
    assert "Фирма" in view._status.text()
    view.deleteLater()


def test_without_a_name_nothing_is_printed(screen) -> None:
    build, _app = screen
    view = build()
    view._firm.setCurrentText("ООО САТУРН")
    view._generate()
    assert "Фамилия" in view._status.text()
    view.deleteLater()


# ------------------------------------------------------------ the number
def test_the_card_number_is_offered_already_moved_on(screen) -> None:
    store.remember_number("АА3915699")
    build, _app = screen
    view = build()
    assert view._card_no.text() == "АА3915701"
    view.deleteLater()


def test_the_numbers_typed_are_still_there_next_time_the_screen_opens(
        screen) -> None:
    """«программани ёпиб очганимда ўчиб кетмасин» — and it does not."""
    build, _app = screen
    view = build()
    view._series.setText("88")
    view._number.setText("3259366")
    view._remember_typed()
    view.deleteLater()

    again = build()
    assert again._series.text() == "88"
    assert again._number.text() == "3259366"
    again.deleteLater()


def test_changing_a_number_replaces_only_that_one(screen) -> None:
    store.remember_typed(series="88", number="3259366")
    build, _app = screen
    view = build()
    view._number.setText("3259400")
    view._remember_typed()
    view.deleteLater()

    again = build()
    assert again._series.text() == "88"
    assert again._number.text() == "3259400"
    again.deleteLater()


# ----------------------------------------------------------- the reading
def test_the_reading_fills_the_boxes_and_the_office_has_the_last_word(
        screen) -> None:
    build, _app = screen
    view = build()
    view._filled(KukPatentData(
        surname="Эргешов", name="Омурбек", patronymic="Куштарович",
        birth_date=date(1998, 6, 16), gender="М", citizenship="Киргизия",
        document="Иностранный паспорт ID3956001"))
    assert view._surname.text() == "Эргешов"
    assert view._citizenship.text() == "Киргизия"
    assert view._born.date().toPython() == date(1998, 6, 16)

    view._surname.setText("Каххоров")          # corrected by hand
    assert view._data().surname == "Каххоров"
    view.deleteLater()


def test_a_worker_without_a_photograph_is_said_out_loud(screen) -> None:
    build, _app = screen
    view = build()
    view._filled(KukPatentData(surname="Эргешов", photo_png=None))
    assert "Расм" in view._status.text()
    view.deleteLater()


# ---------------------------------------------------------- the arranger
def test_both_sides_go_into_the_editor_wearing_their_own_side() -> None:
    from src.ui.views.kukpatent_view import to_fields

    catalogue, samples, fields = to_fields(store.SIDES, {})
    keys = [f.key for f in fields]
    assert f"{FRONT}:surname" in keys and f"{BACK}:issued" in keys
    assert f"{FRONT}:{PHOTO_KEY}" in keys, "расм суриладиган эмас"
    assert f"{BACK}:{PHOTO_KEY}" not in keys, "орқасида расм йўқ"
    assert len(keys) == len(set(keys))
    assert catalogue[f"{BACK}:card_no"].startswith("Орқаси")
    assert samples[f"{FRONT}:surname"]


def test_what_the_editor_leaves_is_what_the_renderer_reads_back() -> None:
    from dataclasses import replace

    from src.pdf.kukpatent_renderer import placed, placed_photo
    from src.ui.views.kukpatent_view import to_fields, to_layout

    _cat, samples, fields = to_fields(store.SIDES, {})
    dragged = {f"{BACK}:issued": (0.30, 0.60, 0.02),
               f"{FRONT}:{PHOTO_KEY}": (0.10, 0.50, 0.30)}
    moved = [replace(f, x=dragged[f.key][0], baseline=dragged[f.key][1],
                     size=dragged[f.key][2]) if f.key in dragged else f
             for f in fields]
    layout = to_layout(moved, samples, store.SIDES)

    assert placed(BACK, layout)["issued"].x == pytest.approx(0.30)
    assert placed(FRONT, layout)["surname"].x != pytest.approx(0.30)
    left, top, _width, height = placed_photo(layout)
    assert (left, height) == (0.10, 0.30)
    assert top == pytest.approx(0.20)


def test_a_restyled_value_keeps_its_weight_and_its_colour() -> None:
    from dataclasses import replace

    from src.pdf.kukpatent_renderer import placed
    from src.ui.views.kukpatent_view import to_fields, to_layout

    _cat, samples, fields = to_fields(store.SIDES, {})
    moved = [replace(f, bold=False, colour=(0.2, 0.3, 0.4), font="Arial")
             if f.key == f"{FRONT}:surname" else f for f in fields]
    slot = placed(FRONT, to_layout(moved, samples, store.SIDES))["surname"]
    assert slot.bold is False
    assert slot.colour == (0.2, 0.3, 0.4)
    assert slot.family == "Arial"


# ------------------------------------------------------------ the blanks
def test_the_screen_reads_back_the_blanks_that_are_uploaded(
        screen, tmp_path) -> None:
    build, _app = screen
    view = build()
    assert view._c.blanks() == {}
    store.set_blank(FRONT, _pdf(tmp_path, "f.pdf"))
    assert set(view._c.blanks()) == {FRONT}
    view.deleteLater()
