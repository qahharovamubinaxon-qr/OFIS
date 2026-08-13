"""«📐 Созлаш» — the arranger every section places its texts in.

Three things the office reported while arranging a form, all of them about
the arranger getting in the way of the work rather than about what prints:

* a new text appeared at the TOP of the blank however far down the form the
  office was working, so every one of them had to be dragged the length of
  the page;
* the page jumped back to the top on every change, so the office lost its
  place after each one;
* the letter spacing could only be nudged a notch at a time, with no way to
  write in a width it had already measured.
"""

from __future__ import annotations

import fitz
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from src.pdf.trud8_fields import Field
from src.ui.widgets import field_editor as fe
from src.ui.widgets.field_editor import A4_MM, PITCH_UNIT, FieldEditor

pytestmark = pytest.mark.usefixtures("qapp")

CATALOGUE = {"surname": "Фамилия", "name": "Исм", "position": "Должность"}
SAMPLES = {"surname": "Исоев", "name": "Аслидин", "position": "Рабочий"}


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture
def pages() -> list[bytes]:
    """Two blank A4 pages, drawn as the arranger draws them."""
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.new_page(width=595, height=842)
    made = [page.get_pixmap(dpi=150).tobytes("png") for page in doc]
    doc.close()
    return made


@pytest.fixture
def editor(pages):
    made = FieldEditor(pages, [Field(key="surname", page=1, x=0.2,
                                     baseline=0.30)],
                       catalogue=CATALOGUE, samples=SAMPLES)
    made.resize(1000, 820)
    made.show()
    yield made
    made.close()


def _click(editor: FieldEditor, x: float, y: float) -> None:
    """Press the blank at that fraction of the page, as the mouse would."""
    canvas = editor._canvas
    at = QPointF(x * canvas._page.width(), y * canvas._page.height())
    canvas.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, at, canvas.mapToGlobal(at),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier))


def _add(editor: FieldEditor, label: str, monkeypatch) -> Field:
    monkeypatch.setattr(fe.QInputDialog, "getItem",
                        staticmethod(lambda *a, **k: (label, True)))
    editor._add()
    return editor.fields()[-1]


# ------------------------------------------------ where a new text lands
def test_a_new_text_lands_where_the_office_clicked(editor, monkeypatch) -> None:
    _click(editor, 0.31, 0.88)                  # low down, on an empty patch
    made = _add(editor, "Исм", monkeypatch)
    assert made.x == pytest.approx(0.31, abs=0.005)
    assert made.baseline == pytest.approx(0.88, abs=0.005)


def test_the_click_still_counts_after_the_page_is_redrawn(editor,
                                                          monkeypatch) -> None:
    """Restyling rebuilds the canvas — the pointed-at spot must survive it."""
    _click(editor, 0.60, 0.72)
    editor._restyle(bold=True)                  # a whole new canvas
    made = _add(editor, "Исм", monkeypatch)
    assert made.x == pytest.approx(0.60, abs=0.005)
    assert made.baseline == pytest.approx(0.72, abs=0.005)


def test_a_click_on_one_page_does_not_place_a_text_on_another(editor,
                                                              monkeypatch):
    _click(editor, 0.60, 0.90)
    editor._pick_page.setCurrentIndex(1)        # 2-саҳифа: never clicked
    made = _add(editor, "Исм", monkeypatch)
    assert made.page == 2
    assert made.baseline != pytest.approx(0.90, abs=0.005)


def test_without_any_click_a_new_text_follows_its_neighbour(editor,
                                                            monkeypatch) -> None:
    """The old behaviour, for an office that adds a text without pointing."""
    made = _add(editor, "Исм", monkeypatch)
    assert made.x == pytest.approx(0.2)          # the picked text's own x
    assert made.baseline == pytest.approx(0.33)  # just under it


def test_a_click_on_an_existing_text_picks_it_up(editor) -> None:
    """Placing must not cost the office the ability to select by mouse."""
    _click(editor, 0.205, 0.305)
    assert editor._picked() == 0


# --------------------------------------------------- keeping one's place
def _scrolled(editor: FieldEditor) -> tuple[int, int]:
    return (editor._scroll.verticalScrollBar().value(),
            editor._scroll.horizontalScrollBar().value())


def _work_far_down(editor: FieldEditor) -> tuple[int, int]:
    editor._set_zoom(2.0)                        # so the page really scrolls
    down, across = (editor._scroll.verticalScrollBar(),
                    editor._scroll.horizontalScrollBar())
    assert down.maximum() and across.maximum(), "саҳифа сурилмаяпти"
    down.setValue(int(down.maximum() * 0.8))
    across.setValue(int(across.maximum() * 0.5))
    return _scrolled(editor)


def test_changing_a_text_does_not_scroll_the_blank_away(editor) -> None:
    was = _work_far_down(editor)
    editor._restyle(bold=True)
    assert _scrolled(editor) == was


def test_adding_a_text_does_not_scroll_the_blank_away(editor,
                                                      monkeypatch) -> None:
    was = _work_far_down(editor)
    _click(editor, 0.31, 0.88)
    _add(editor, "Исм", monkeypatch)
    assert _scrolled(editor) == was


def test_turning_to_another_page_starts_at_the_top(editor) -> None:
    _work_far_down(editor)
    editor._pick_page.setCurrentIndex(1)
    assert _scrolled(editor) == (0, 0)


# --------------------------------------------------- spacing, by number
def test_the_spacing_can_be_written_in_as_a_number(editor) -> None:
    editor._pitch_shown.setValue(96.5)
    assert editor.fields()[0].pitch == pytest.approx(96.5 / PITCH_UNIT)


def test_the_written_spacing_is_shown_in_millimetres_too(editor) -> None:
    """So it can be checked against a ruler on the blank itself."""
    editor._pitch_shown.setValue(25.0)
    assert f"{25.0 / PITCH_UNIT * A4_MM:.1f}" in editor._pitch_mm.text()


def test_zero_means_ordinary_text(editor) -> None:
    editor._pitch_shown.setValue(50.0)
    editor._pitch_shown.setValue(0.0)
    assert editor.fields()[0].pitch == 0.0
    assert editor._pitch_shown.text() == "оддий"
    assert editor._pitch_mm.text() == ""


def test_the_buttons_and_the_number_are_the_same_setting(editor) -> None:
    editor._pitch_shown.setValue(96.5)
    editor._nudge_pitch(+1)
    assert editor._pitch_shown.value() == pytest.approx(
        96.5 + fe.PITCH_STEP * PITCH_UNIT)
    assert editor.fields()[0].pitch == pytest.approx(
        0.0965 + fe.PITCH_STEP, abs=1e-6)


def test_the_number_shows_the_picked_text_own_spacing(pages) -> None:
    made = FieldEditor(pages,
                       [Field(key="surname", page=1, pitch=0.037),
                        Field(key="name", page=1, pitch=0.0)],
                       catalogue=CATALOGUE, samples=SAMPLES)
    made.show()
    assert made._pitch_shown.value() == pytest.approx(37.0)
    made._pick_item.setCurrentIndex(made._pick_item.findData(1))
    assert made._pitch_shown.text() == "оддий"
    made.close()


def test_showing_a_spacing_never_changes_it(pages) -> None:
    """Filling the box in must not be mistaken for the office typing in it."""
    made = FieldEditor(pages, [Field(key="surname", page=1, pitch=0.037)],
                       catalogue=CATALOGUE, samples=SAMPLES)
    made.show()
    made._pick_page.setCurrentIndex(1)
    made._pick_page.setCurrentIndex(0)
    assert made.fields()[0].pitch == pytest.approx(0.037)
    made.close()
