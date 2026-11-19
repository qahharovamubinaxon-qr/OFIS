"""Бош экран: бўлимлар рўйхати ва ҳалқали кўрсаткич.

Офис дастурни очганда биринчи кўрадигани — бўлимлар карточкаси. Карточкалар
рўйхати АЛОҲИДА сақланмайди: навигация жадвалидан ўқилади, акс ҳолда янги
бўлим қўшилганда биттаси янгиланиб, иккинчиси эскилигича қоларди.
"""

from __future__ import annotations

import pytest

from src.ui.sections import Section, grouped, matches, sections_from_nav

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


_NAV_SAMPLE = [
    (None, "nav.dashboard", "Dashboard", "Бугунги иш", "📊"),
    ("МИГРАЦИЯ", "nav.process", "Process Employee", "Ҳужжат → PDF", "🛂"),
    (None, "nav.registration", "Registration", "Уведомление о прибытии", "🏠"),
    (None, "nav.patent", "ПАТЕНТ", "Патент картаси", "🩷"),
    ("НОТАРИУС", "nav.dover", "Доверенность", "Нотариал ҳужжат", "📜"),
    ("БАЗА", "nav.companies", "Companies", "Фирмалар", "🏢"),
    (None, "nav.archive", "Archive", "Архив", "🗄"),
]


# ------------------------------------------------------------- бўлимлар
def test_sections_come_from_the_navigation_itself() -> None:
    keys = [s.key for s in sections_from_nav(_NAV_SAMPLE)]
    assert keys == ["nav.process", "nav.registration", "nav.patent", "nav.dover"]


def test_data_sections_are_not_work_cards() -> None:
    """Dashboard, фирмалар, архив — карточка эмас: улар иш чиқармайди."""
    keys = [s.key for s in sections_from_nav(_NAV_SAMPLE)]
    assert "nav.dashboard" not in keys
    assert "nav.companies" not in keys
    assert "nav.archive" not in keys


def test_a_section_carries_the_heading_above_it() -> None:
    by_key = {s.key: s for s in sections_from_nav(_NAV_SAMPLE)}
    assert by_key["nav.registration"].group == "МИГРАЦИЯ"   # сарлавҳасиз қатор
    assert by_key["nav.dover"].group == "НОТАРИУС"


def test_the_real_navigation_is_read_without_a_second_list() -> None:
    from src.ui.main_window import _NAV

    sections = sections_from_nav(_NAV)
    assert len(sections) > 25, "бўлимлар жадвалдан ўқилмади"
    assert all(s.title and s.icon for s in sections)
    assert "nav.registration" in {s.key for s in sections}


def test_cards_keep_the_order_the_office_learned() -> None:
    blocks = grouped(sections_from_nav(_NAV_SAMPLE))
    assert [name for name, _ in blocks] == ["МИГРАЦИЯ", "НОТАРИУС"]
    assert [s.key for s in blocks[0][1]] == [
        "nav.process", "nav.registration", "nav.patent"]


# -------------------------------------------------------------- қидирув
def _s(title: str, subtitle: str = "", key: str = "nav.x") -> Section:
    return Section(key=key, title=title, subtitle=subtitle, icon="📄", group="")


def test_search_finds_a_section_by_its_name() -> None:
    assert matches(_s("ПАТЕНТ"), "патент")
    assert not matches(_s("ПАТЕНТ"), "страховка")


def test_search_ignores_the_case_and_the_spaces() -> None:
    assert matches(_s("ПАТЕНТ"), "  ПаТеНт  ")


def test_search_also_looks_at_what_the_section_does() -> None:
    """Оператор «уведомление» деб ёзади — бўлим номи эса «Регистрация»."""
    assert matches(_s("Регистрация", "Уведомление о прибытии"), "уведомление")


def test_an_empty_search_hides_nothing() -> None:
    assert matches(_s("ПАТЕНТ"), "")
    assert matches(_s("ПАТЕНТ"), "   ")


# -------------------------------------------------------- ҳалқали кўрсаткич
def test_the_ring_fills_by_what_it_is_given() -> None:
    from src.ui.widgets.ring_gauge import RingGauge

    ring = RingGauge()
    ring.set_progress(0.25)
    assert ring.span_degrees() == 90


def test_the_ring_never_wraps_around_itself() -> None:
    """Режадан ошиб кетилса ҳалқа иккинчи марта айланмайди."""
    from src.ui.widgets.ring_gauge import RingGauge

    ring = RingGauge()
    ring.set_progress(1.8)
    assert ring.progress() == 1.0
    ring.set_progress(-3)
    assert ring.progress() == 0.0


def test_the_middle_says_the_percent_of_a_fraction() -> None:
    from src.ui.widgets.ring_gauge import RingGauge

    ring = RingGauge()
    ring.set_fraction(248, 345)
    assert ring.centre_text() == "72"
    assert 0.71 < ring.progress() < 0.72


def test_nothing_to_measure_is_said_not_guessed(qapp) -> None:
    """Режа киритилмаган бўлса — ноль эмас, «—»: бўлинма йўқ."""
    from src.ui.widgets.ring_gauge import RingGauge

    ring = RingGauge()
    ring.set_fraction(5, 0)
    assert ring.centre_text() == "—"
    assert ring.progress() == 0.0


def test_a_count_is_not_forced_to_be_a_percent() -> None:
    """«Бугун 12» — бу 12 % эмас: ҳалқа ва ўртадаги сон алоҳида."""
    from src.ui.widgets.ring_gauge import RingGauge

    ring = RingGauge()
    ring.set_centre("12")
    ring.set_progress(0.4)
    assert ring.centre_text() == "12"
    assert ring.span_degrees() == pytest.approx(144)


# --------------------------------------------------------------- бош экран
class _Archive:
    """Архив — ҳақиқий сонлар ўрнига.

    `busiest_day` ҳам шу ерда: бош экрандаги ҳалқа ўйлаб топилган режага эмас,
    офиснинг ЎЗ энг банд кунига нисбатан тўлади.
    """

    def __init__(self, today: int = 3, busiest: int = 6) -> None:
        self._today, self._busiest = today, busiest

    def count_today(self) -> int:
        return self._today

    def count_total(self) -> int:
        return 120

    def busiest_day(self, days: int = 14) -> int:
        return self._busiest

    def recent(self, limit: int = 6):
        return []


class _Firms:
    def count(self) -> int:
        return 4


class _Numbers:
    def next_reg_number(self) -> int:
        return 346


def _home(today: int = 3, busiest: int = 6):
    from src.ui.views.dashboard_view import DashboardView

    return DashboardView(_Archive(today, busiest), _Firms(), _Numbers(),
                         sections_from_nav(_NAV_SAMPLE), "dark")


def _all_cards(view):
    return [c for _h, g in view._groups for c in g.cards()]


def test_every_section_gets_a_card(qapp) -> None:
    view = _home()
    assert [c.section.key for c in _all_cards(view)] == [
        "nav.process", "nav.registration", "nav.patent", "nav.dover"]


def test_a_card_wears_the_colour_of_its_own_paper(qapp) -> None:
    from src.ui.theme import stock_for

    by_key = {c.section.key: c for c in _all_cards(_home())}
    assert by_key["nav.patent"]._colour.name().upper() == \
        stock_for("nav.patent", "dark").base.upper()
    assert by_key["nav.patent"]._colour != by_key["nav.registration"]._colour


def test_pressing_a_card_opens_that_section(qapp) -> None:
    view = _home()
    opened: list[str] = []
    view.section_chosen.connect(opened.append)
    next(c for c in _all_cards(view) if c.section.key == "nav.patent").click()
    assert opened == ["nav.patent"]


def test_search_leaves_only_what_was_asked_for(qapp) -> None:
    view = _home()
    view._search.setText("патент")
    left = [c.section.key for _h, g in view._groups for c in g.visible_cards()]
    assert left == ["nav.patent"]


def test_clearing_the_search_brings_everything_back(qapp) -> None:
    view = _home()
    view._search.setText("патент")
    view._search.setText("")
    left = [c.section.key for _h, g in view._groups for c in g.visible_cards()]
    assert len(left) == 4


def test_a_search_that_finds_nothing_says_so(qapp) -> None:
    view = _home()
    view._search.setText("вертолёт")
    assert view._empty.isVisible() or view._empty.isVisibleTo(view)


def test_the_ring_measures_today_against_the_busiest_day(qapp) -> None:
    view = _home(today=3, busiest=6)
    assert view._ring.centre_text() == "3"
    assert view._ring.progress() == pytest.approx(0.5)


def test_a_first_day_does_not_fake_a_full_ring(qapp) -> None:
    """Архив бўш — ҳалқа тўла эмас, ноль."""
    view = _home(today=0, busiest=0)
    assert view._ring.progress() == 0.0
    assert view._ring.centre_text() == "0"


# ------------------------------------------------------- карточка → бўлим
def test_a_card_selects_the_sidebar_row_of_its_section() -> None:
    """Карточка бўлимни ЁНДАГИ рўйхат орқали очади — ранг, сарлавҳа ва
    статус қатори шунда ўзи эргашади."""
    from types import SimpleNamespace

    from src.ui.main_window import MainWindow

    chosen: list[int] = []
    window = SimpleNamespace(
        _row_to_key={1: "nav.process", 3: "nav.registration"},
        _nav_list=SimpleNamespace(setCurrentRow=chosen.append))
    assert MainWindow.open_section(window, "nav.registration") is True
    assert chosen == [3]


def test_an_unknown_section_is_refused_not_guessed() -> None:
    from types import SimpleNamespace

    from src.ui.main_window import MainWindow

    chosen: list[int] = []
    window = SimpleNamespace(
        _row_to_key={1: "nav.process"},
        _nav_list=SimpleNamespace(setCurrentRow=chosen.append))
    assert MainWindow.open_section(window, "nav.yoq") is False
    assert chosen == []


# ------------------------------------------------------------ энг банд кун
def test_the_busiest_day_is_read_from_the_archive(tmp_path) -> None:
    from datetime import date, timedelta

    from src.database.connection import Database
    from src.database.repositories.generated_repo import GeneratedRepository

    db = Database(tmp_path / "g.db")
    db.migrate()
    repo = GeneratedRepository(db)
    for i in range(3):
        repo.add(company_id="c", company_name="ООО", surname=f"A{i}",
                 full_name=f"A{i} B", citizenship="УЗБ", reg_number=100 + i,
                 pdf_path=f"{i}.pdf", form_date=date.today())
    assert repo.busiest_day() == 3
    assert repo.count_today() == 3
    db.close()


def test_an_empty_archive_has_no_busiest_day(tmp_path) -> None:
    from src.database.connection import Database
    from src.database.repositories.generated_repo import GeneratedRepository

    db = Database(tmp_path / "e.db")
    db.migrate()
    assert GeneratedRepository(db).busiest_day() == 0
    db.close()
