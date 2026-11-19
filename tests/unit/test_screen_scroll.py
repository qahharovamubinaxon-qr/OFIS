"""Бўлим ойнага сиғмаса — ўрам (скролл), сиқилиш эмас.

Офис суратга олиб юборди: МИГ бўлимида матн катакчалари ўз ёрлиқларининг
УСТИГА чиқиб кетган — «ФАМИЛИЯ:» ёзуви устидан фамилия босилиб, ҳеч нарса
ўқилмайди. Сабаби оддий: экранда ўрам йўқ эди, ва ойна бўйи етмаганда Qt
қаторларни бир-бирига сиқиб юборади.

Энди ҳар бўлим ўрам ичида осилиб туради: ўз бўйини сақлайди, ортиғи пастга
айлантириб кўрилади.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _tall_screen(rows: int = 20):
    """Бўйи ойнага сиғмайдиган бўлим — МИГ каби."""
    from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

    screen = QWidget()
    column = QVBoxLayout(screen)
    for i in range(rows):
        column.addWidget(QLabel(f"МАЙДОН {i}:"))
        box = QLineEdit()
        box.setMinimumHeight(32)
        column.addWidget(box)
    return screen


def test_a_screen_taller_than_the_window_is_not_squeezed(qapp) -> None:
    """Бўлимнинг тўлиқ бўйи сақланади: кўринадиган қисм + айлантириш оралиғи
    унинг керакли бўйидан кам бўлмаслиги керак. Қисилса — катакчалар ёрлиқлар
    устига чиқади, офис суратга олиб юборган нарса шу эди."""
    from src.ui.widgets.screen_scroll import ScrollHost

    screen = _tall_screen()
    needed = screen.minimumSizeHint().height()
    host = ScrollHost(screen)
    host.resize(900, 300)
    host.show()
    qapp.processEvents()
    assert needed > 300, "тест экрани етарлича баланд эмас"
    reachable = host.viewport().height() + host.verticalScrollBar().maximum()
    # бир неча пиксель — ўрам майдонининг чети; сиқилиш эса юзлаб пиксель
    assert reachable >= needed - 8, f"бўлим сиқилиб қолди: {reachable} < {needed}"
    host.hide()


def test_what_does_not_fit_can_be_scrolled_to(qapp) -> None:
    from src.ui.widgets.screen_scroll import ScrollHost

    host = ScrollHost(_tall_screen())
    host.resize(900, 300)
    host.show()
    qapp.processEvents()
    assert host.verticalScrollBar().maximum() > 0, "пастга айлантириб бўлмайди"
    host.hide()


def test_a_screen_that_fits_is_left_alone(qapp) -> None:
    from src.ui.widgets.screen_scroll import ScrollHost

    host = ScrollHost(_tall_screen(rows=2))
    host.resize(900, 800)
    host.show()
    qapp.processEvents()
    assert host.verticalScrollBar().maximum() == 0, "керак бўлмаган ўрам чиқди"
    host.hide()


def test_a_tall_window_is_still_filled_by_the_screen(qapp) -> None:
    """Ўрам бўлимни ўз бўйига қисиб қўймайди: баланд ойнада у тўлдиради,
    акс ҳолда қисқа бўлим тепада осилиб, ости бўш қоларди."""
    from src.ui.widgets.screen_scroll import ScrollHost

    screen = _tall_screen(rows=2)
    host = ScrollHost(screen)
    host.resize(900, 700)
    host.show()
    qapp.processEvents()
    assert screen.height() > screen.minimumSizeHint().height()
    assert screen.height() >= host.viewport().height() - 2
    host.hide()


# ------------------------------------------------- ойна бўлимни топа олсин
def test_the_shell_reaches_the_screen_through_its_host(qapp) -> None:
    from PySide6.QtWidgets import QWidget

    from src.ui.widgets.screen_scroll import ScrollHost, screen_of

    screen = QWidget()
    assert screen_of(ScrollHost(screen)) is screen


def test_an_unwrapped_screen_is_returned_as_it_is(qapp) -> None:
    from PySide6.QtWidgets import QWidget

    from src.ui.widgets.screen_scroll import screen_of

    screen = QWidget()
    assert screen_of(screen) is screen
    assert screen_of(None) is None


def test_refresh_and_reset_still_find_the_real_screen(qapp) -> None:
    """`refresh()` ва `reset()` ўрамга эмас, БЎЛИМГА боради."""
    from types import SimpleNamespace

    from PySide6.QtWidgets import QWidget

    from src.ui.main_window import MainWindow
    from src.ui.widgets.screen_scroll import ScrollHost

    class _Screen(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.refreshed = False

        def refresh(self) -> None:
            self.refreshed = True

    screen = _Screen()
    host = ScrollHost(screen)
    window = SimpleNamespace(_stack=SimpleNamespace(currentWidget=lambda: host))
    found = MainWindow.current_view(window)
    assert found is screen
    found.refresh()
    assert screen.refreshed
