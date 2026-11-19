"""The home screen: every section as a card, with today's figures above them.

What the office opens the program to do is pick a section, so that is what the
first screen is — the forty sections laid out as cards, each in the colour of
the paper it prints, grouped the way the sidebar groups them, with a search
box above for the days when the hand is faster than the eye.

The figures at the top are the ones that are TRUE. The program knows how many
documents went out today, how many in all, and which number the next one
takes; it does not know a daily target, so the ring is filled against the
office's own busiest day of the last fortnight rather than an invented quota —
a ring that measures nothing is a decoration, and this program does not
decorate.

The cards carry no per-section counter for the same reason: the archive
records which company a document was made for, not which section made it, so
a «today · 3» under every card would be a number nobody could stand behind.
The subtitle goes there instead — what the section actually does.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.database.repositories.generated_repo import GeneratedRepository
from src.services.company_service import CompanyService
from src.services.generation_service import GenerationService
from src.ui.sections import Section, grouped, matches
from src.ui.theme import MACHINE, stock_for
from src.ui.widgets.ring_gauge import RingGauge
from src.ui.widgets.section_card import DAY, NIGHT, SectionCard

#: How wide a card wants to be before the grid gives it a neighbour.
_CARD_ROOM = 250
_MIN_COLUMNS = 2
_MAX_COLUMNS = 6


def _tile(title: str, value: str) -> tuple[QWidget, QLabel]:
    """A plain figure, and the label to write new values into."""
    box = QWidget()
    box.setObjectName("statCard")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(18, 14, 18, 14)
    lay.setSpacing(6)
    v = QLabel(value)
    v.setObjectName("statValue")
    t = QLabel(title)
    t.setObjectName("statLabel")
    lay.addWidget(v)
    lay.addWidget(t)
    return box, v


class _SectionGrid(QWidget):
    """The cards of one group, re-flowed to however many fit across."""

    def __init__(self, cards: list[SectionCard]) -> None:
        super().__init__()
        self._cards = cards
        # which cards the search left standing. Kept here rather than read
        # back from Qt: a child widget counts as hidden until its parent is
        # first shown, so asking the widget would lay out an empty grid on
        # the way up.
        self._visible = list(cards)
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(12)
        for card in cards:
            card.setParent(self)

    def cards(self) -> list[SectionCard]:
        return list(self._cards)

    def visible_cards(self) -> list[SectionCard]:
        return list(self._visible)

    def set_columns(self, columns: int) -> None:
        if columns == self._columns:
            return
        self._columns = columns
        self._reflow()

    def filter(self, query: str) -> int:
        """Show the cards that answer ``query``; returns how many are left."""
        keep = [c for c in self._cards if matches(c.section, query)]
        kept = set(id(c) for c in keep)
        for card in self._cards:
            card.setVisible(id(card) in kept)
        self._visible = keep
        self._reflow()
        return len(keep)

    def _reflow(self) -> None:
        columns = max(1, self._columns)
        while self._grid.count():
            self._grid.takeAt(0)
        for index, card in enumerate(self._visible):
            self._grid.addWidget(card, index // columns, index % columns)
        for column in range(columns):
            self._grid.setColumnStretch(column, 1)


class DashboardView(QWidget):
    """Every section, one press away."""

    #: the nav key of the card that was pressed
    section_chosen = Signal(str)

    def __init__(
        self,
        generated: GeneratedRepository,
        companies: CompanyService,
        gen: GenerationService,
        sections: list[Section] | None = None,
        theme: str = "dark",
    ) -> None:
        super().__init__()
        self._generated = generated
        self._companies = companies
        self._gen = gen
        self._sections = list(sections or [])
        self._theme = theme
        self._columns = 0
        self._groups: list[tuple[QLabel, _SectionGrid]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(16)
        root.addLayout(self._build_head())
        root.addLayout(self._build_figures())
        root.addWidget(self._build_cards(), stretch=1)

        self.refresh()

    # ---------------------------------------------------------------- head
    def _build_head(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        title = QLabel("OFIS 24/7")
        title.setObjectName("viewTitle")
        subtitle = QLabel("Бўлимни танланг — ёки номини ёзиб топинг")
        subtitle.setObjectName("viewSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        row.addLayout(titles)
        row.addStretch(1)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Қидириш:  патент, регистрация, ДМС…")
        self._search.setClearButtonEnabled(True)
        self._search.setMinimumWidth(280)
        self._search.setMaximumWidth(420)
        self._search.textChanged.connect(self._filter)
        row.addWidget(self._search)
        return row

    # ------------------------------------------------------------- figures
    def _build_figures(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        today = QWidget()
        today.setObjectName("statCard")
        lay = QHBoxLayout(today)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)
        self._ring = RingGauge(diameter=72)
        lay.addWidget(self._ring)
        side = QVBoxLayout()
        side.setSpacing(5)
        self._today_value = QLabel("0")
        self._today_value.setObjectName("statValue")
        self._today_note = QLabel("БУГУН")
        self._today_note.setObjectName("statLabel")
        side.addWidget(self._today_value)
        side.addWidget(self._today_note)
        lay.addLayout(side)
        row.addWidget(today)

        total, self._total_value = _tile("ЖАМИ ҲУЖЖАТ", "0")
        row.addWidget(total)
        nxt, self._next_value = _tile("КЕЙИНГИ №", "0")
        row.addWidget(nxt)
        firms, self._firms_value = _tile("ФИРМА", "0")
        row.addWidget(firms)

        recent_box = QWidget()
        recent_box.setObjectName("statCard")
        rl = QVBoxLayout(recent_box)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(6)
        caption = QLabel("ОХИРГИ ИШЛАР")
        caption.setObjectName("statLabel")
        rl.addWidget(caption)
        self._recent = QListWidget()
        self._recent.setObjectName("homeRecent")
        self._recent.setFixedHeight(76)
        rl.addWidget(self._recent)
        row.addWidget(recent_box, stretch=1)
        return row

    # --------------------------------------------------------------- cards
    def _build_cards(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("homeScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 2, 6, 6)
        column.setSpacing(14)

        ink = DAY if self._theme == "light" else NIGHT
        for name, members in grouped(self._sections):
            heading = QLabel(name or "БЎЛИМЛАР")
            heading.setObjectName("fieldLabel")
            cards = []
            for section in members:
                card = SectionCard(
                    section, stock_for(section.key, self._theme).base, ink)
                card.set_count(None)
                card.chosen.connect(self.section_chosen.emit)
                cards.append(card)
            grid = _SectionGrid(cards)
            column.addWidget(heading)
            column.addWidget(grid)
            self._groups.append((heading, grid))

        self._empty = QLabel("Бундай бўлим йўқ — бошқа сўз билан ёзиб кўринг.")
        self._empty.setObjectName("viewSubtitle")
        self._empty.setVisible(False)
        column.addWidget(self._empty)
        column.addStretch(1)

        scroll.setWidget(holder)
        return scroll

    # -------------------------------------------------------------- living
    def resizeEvent(self, event) -> None:                      # noqa: N802
        super().resizeEvent(event)
        room = max(1, self.width() - 60)
        columns = max(_MIN_COLUMNS, min(_MAX_COLUMNS, room // _CARD_ROOM))
        if columns != self._columns:
            self._columns = columns
            for _heading, grid in self._groups:
                grid.set_columns(columns)

    def _filter(self, query: str) -> None:
        found = 0
        for heading, grid in self._groups:
            shown = grid.filter(query)
            heading.setVisible(shown > 0)
            grid.setVisible(shown > 0)
            found += shown
        self._empty.setVisible(found == 0)

    def set_theme(self, theme: str) -> None:
        """Re-ink the cards when the window changes between day and night."""
        self._theme = theme
        ink = DAY if theme == "light" else NIGHT
        for _heading, grid in self._groups:
            for card in grid.cards():
                card.set_ink(ink)
                card.set_colour(stock_for(card.section.key, theme).base)
        self._paint_ring()

    def _paint_ring(self) -> None:
        machine = MACHINE.get(self._theme, MACHINE["dark"])
        track = "#1C2733" if self._theme != "light" else "#DCE4E9"
        ink = "#E8EEF2" if self._theme != "light" else "#10212B"
        muted = "#60707E" if self._theme != "light" else "#6B8291"
        self._ring.set_colours(machine, track, ink, muted)

    def refresh(self) -> None:
        today = self._generated.count_today()
        busiest = self._generated.busiest_day()
        self._ring.set_progress(today / busiest if busiest else 0.0)
        self._ring.set_centre(str(today))
        self._paint_ring()

        self._today_value.setText(str(today))
        self._today_note.setText(
            "БУГУН" if not busiest else f"БУГУН  ·  энг банд кун: {busiest}")
        self._total_value.setText(str(self._generated.count_total()))
        self._next_value.setText(str(self._gen.next_reg_number()))
        self._firms_value.setText(str(self._companies.count()))

        self._recent.clear()
        for record in self._generated.recent(6):
            self._recent.addItem(
                f"№{record.reg_number}  ·  {record.full_name}  ·  {record.company_name}")
