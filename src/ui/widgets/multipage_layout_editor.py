"""«Матнларни жойлаш» over a many-page blank — one dialog, page by page.

The МВД ТРУДАВОЙ packet is ten pages, and its values live on eight of them.
One :class:`LayoutEditor`-style canvas per page would mean ten dialogs in a
row; instead this one dialog holds a page picker — «Саҳифа», олдинги /
кейингиси — and swaps the canvas under the same controls, harvesting each
page's positions as the operator leaves it. Nothing is lost by moving around:
OK returns everything from every page visited or not.
"""

from __future__ import annotations

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from src.ui.widgets.layout_editor import Item, Result, _Canvas


class MultiPageLayoutEditor(QDialog):
    """Drag every page's values into place without leaving the dialog."""

    def __init__(self, pages: list[bytes], items_by_page: dict[int, list[Item]],
                 title: str = "Матнларни жойлаш", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{title} — сичқонча билан суринг")
        self.setMinimumSize(920, 800)

        self._pixmaps: list[QPixmap] = []
        for png in pages:
            pixmap = QPixmap()
            pixmap.loadFromData(png)
            self._pixmaps.append(pixmap)
        self._items = {page: list(items) for page, items in items_by_page.items()}
        #: everything already harvested, keyed the way the spec keys slots —
        #: page keys never collide, so one flat dict carries the whole packet
        self._collected: dict[str, list[float]] = {}
        self._page = 0
        self._canvas: _Canvas | None = None

        outer = QVBoxLayout(self)
        hint = QLabel(
            "Матнни босиб ушлаб суринг; ғилдирак ёки ＋/－ — катта-кичик; "
            "ўқ тугмалари — аниқ суриш.\n"
            "Саҳифани алмаштиринг — қилган ишингиз сақланиб туради; "
            "OK ҳамма саҳифани бирдан сақлайди.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a94a3;")
        outer.addWidget(hint)

        nav = QHBoxLayout()
        nav.addWidget(QLabel("Саҳифа:"))
        self._pick_page = QComboBox()
        for page in sorted(self._items):
            count = len(self._items[page])
            self._pick_page.addItem(f"{page}-саҳифа  ({count} та матн)", page)
        nav.addWidget(self._pick_page, stretch=1)
        back = QPushButton("⬅ Олдинги")
        back.clicked.connect(lambda: self._step(-1))
        nav.addWidget(back)
        ahead = QPushButton("Кейингиси ➡")
        ahead.clicked.connect(lambda: self._step(+1))
        nav.addWidget(ahead)
        bigger = QPushButton("＋ катта")
        bigger.clicked.connect(lambda: self._canvas and
                               self._canvas.resize_picked(1))
        nav.addWidget(bigger)
        smaller = QPushButton("－ кичик")
        smaller.clicked.connect(lambda: self._canvas and
                                self._canvas.resize_picked(-1))
        nav.addWidget(smaller)
        outer.addLayout(nav)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        outer.addWidget(self._scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._pick_page.currentIndexChanged.connect(self._on_pick)
        if self._pick_page.count():
            self._show(self._pick_page.itemData(0))

    # ------------------------------------------------------------ pages
    def _step(self, delta: int) -> None:
        index = self._pick_page.currentIndex() + delta
        if 0 <= index < self._pick_page.count():
            self._pick_page.setCurrentIndex(index)

    def _on_pick(self, index: int) -> None:
        page = self._pick_page.itemData(index)
        if page is not None:
            self._show(page)

    def _harvest(self) -> None:
        """Keep where the current page's values are before leaving it."""
        if self._canvas is None:
            return
        for key, item in self._canvas.items.items():
            self._collected[key] = [item.x, item.baseline, item.size]

    def _show(self, page: int) -> None:
        self._harvest()
        self._page = page
        items = []
        for item in self._items.get(page, []):
            moved = self._collected.get(item.key)
            if moved:
                item = Item(key=item.key, label=item.label, sample=item.sample,
                            x=moved[0], baseline=moved[1], size=moved[2],
                            colour=item.colour, font_family=item.font_family,
                            bold=item.bold)
            items.append(item)
        self._canvas = _Canvas(self._pixmaps[page - 1], items, [])
        self._scroll.setWidget(self._canvas)

    # ------------------------------------------------------------ result
    def result(self) -> Result:
        self._harvest()
        return Result(items=dict(self._collected))
