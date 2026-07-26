"""The Обновить button: clearing a view's uploads without restarting."""

from __future__ import annotations

import tempfile

import pytest

from src.config import paths


@pytest.fixture()
def window(monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()

    from PySide6.QtWidgets import QApplication

    from src.app import build_container
    from src.ui.i18n import Translator
    from src.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    win = MainWindow(build_container(), Translator("uz"))
    yield win
    win.deleteLater()
    app.processEvents()
    paths.data_dir.cache_clear()


def _view(window, class_name: str):
    for page in range(window._stack.count()):
        widget = window._stack.widget(page)
        if widget.__class__.__name__ == class_name:
            return widget
    raise AssertionError(f"{class_name} not found")


def _show(window, view) -> None:
    for row, page in window._row_to_page.items():
        if window._stack.widget(page) is view:
            window._nav_list.setCurrentRow(row)
            return


def test_reset_clears_multi_drop_uploads(window, tmp_path) -> None:
    from pathlib import Path

    view = _view(window, "UmumiyView")
    _show(window, view)

    pdf = tmp_path / "dogovor.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    photo = tmp_path / "passport.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0")
    view._dz_doc._add([Path(pdf)])
    view._dz_worker._add([Path(photo)])
    assert view._dz_doc.files and view._dz_worker.files

    window.reset_current_view()
    assert view._dz_doc.files == []
    assert view._dz_worker.files == []


def test_reset_clears_single_drop_zones(window, tmp_path) -> None:
    from pathlib import Path

    view = _view(window, "ProcessView")
    _show(window, view)

    photo = tmp_path / "passport.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xe0")
    view._dz_passport._set_path(Path(photo))
    assert view._dz_passport.path is not None

    window.reset_current_view()
    assert view._dz_passport.path is None


def test_reset_uses_a_views_own_reset_when_present(window) -> None:
    view = _view(window, "SummaView")
    _show(window, view)

    view._sum.setText("27500,50")
    assert "Двадцать семь тысяч" in view._sum_out.text()

    window.reset_current_view()
    assert view._sum.text() == ""


def test_summa_view_converts_live(window) -> None:
    view = _view(window, "SummaView")
    view._sum.setText("10000")
    assert view._sum_out.text() == "Десять тысяч рублей 00 копеек"
    assert "10 000,00" in view._sum_digits.text()
    assert "года" in view._date_out.text()
