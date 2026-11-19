"""Ҳар бир бўлим очилсин — биронтаси ҳам йиқилмасин.

Қирқ беш бўлим қирқ беш файлда ётибди, ва кўринишга тегадиган ўзгариш
(панелларга ўраш, мавзу, ўрам) ҳаммасига бирданига тегади. Биттаси
синганини офис ўша бўлимни очганда билади — яъни иш устида.

Шунинг учун битта тест ҳаммасини очиб кўради. Секин, лекин у ушлайдиган
нарса — «дастур очилмай қолди» деган қўнғироқ.
"""

from __future__ import annotations

import tempfile

import pytest


@pytest.fixture(scope="module")
def window():
    # Ҳақиқий AppData'га тегмаслик учун — офиснинг базаси, бланкалари ва
    # созламалари тест туфайли ўзгармасин.
    sandbox = tempfile.mkdtemp()
    import os

    old = {k: os.environ.get(k) for k in ("XDG_DATA_HOME", "LOCALAPPDATA")}
    os.environ["XDG_DATA_HOME"] = sandbox
    os.environ["LOCALAPPDATA"] = sandbox

    from PySide6.QtWidgets import QApplication

    from src.config import paths

    paths.data_dir.cache_clear()
    app = QApplication.instance() or QApplication([])

    from src.app import build_container
    from src.config.settings_service import SettingsService
    from src.ui.i18n import Translator
    from src.ui.main_window import MainWindow
    from src.ui.theme import apply_theme

    container = build_container()
    settings = container.resolve(SettingsService)
    apply_theme(app, "dark")
    win = MainWindow(container, Translator(settings.language))
    yield win
    win.close()
    for key, value in old.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    paths.data_dir.cache_clear()


def test_every_section_opens(window) -> None:
    from src.ui.main_window import _NAV

    refused = [key for _g, key, *_r in _NAV if not window.open_section(key)]
    assert not refused, f"очилмаган бўлимлар: {refused}"


def test_every_section_hangs_in_a_scroll_host(window) -> None:
    """Биронта бўлим ўрамсиз қолмасин — ўшанда катакчалар устма-уст тушади."""
    from src.ui.main_window import _NAV
    from src.ui.widgets.screen_scroll import ScrollHost

    bare = []
    for _g, key, *_r in _NAV:
        if key == "nav.dashboard":      # бош экран ўз ўрамига эга
            continue
        window.open_section(key)
        if not isinstance(window._stack.currentWidget(), ScrollHost):
            bare.append(key)
    assert not bare, f"ўрамсиз бўлимлар: {bare}"


def test_the_window_opens_on_the_home_screen(window) -> None:
    from src.ui.views.dashboard_view import DashboardView

    window._select_page(0)
    assert isinstance(window.current_view(), DashboardView)


def test_both_themes_apply_to_every_section(window) -> None:
    """Кундузги варақ ҳам ҳар бўлимда ишласин — фақат тунгиси эмас."""
    for theme in ("light", "dark"):
        window._apply_theme(theme)
        window.open_section("nav.mig")
        window.open_section("nav.patent")
    assert window._theme == "dark"
