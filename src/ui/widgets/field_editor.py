"""One window for the whole blank: add a text, say what it means, place it.

Everything the office does to its own blank happens here and nowhere else —
adding a text and choosing its meaning from the list, dragging it, sizing
it, its colour, its weight, its face, and deleting it. The page picture
under it is the blank itself, so what is on screen is what comes out of the
printer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
)

from src.pdf.fonts import families
from src.pdf.trud8_fields import CATALOGUE, Field
from src.ui.widgets.layout_editor import Item, _Canvas

WEIGHTS = ("Юпқа (оддий)", "Қалин (жирний)")
#: Which way a text lies. Blanks that are written up their own edge — a
#: медкнижка has several — are turned here rather than in code.
TURNS: tuple[tuple[str, int], ...] = (
    ("↔ Ётиқ", 0), ("↑ Тик (пастдан)", 90), ("↓ Тик (тепадан)", 270))


class _PickCanvas(_Canvas):
    """The drag canvas, which now says out loud what the mouse picked."""

    picked_key = Signal(str)

    def mousePressEvent(self, event) -> None:      # noqa: N802 - Qt override
        super().mousePressEvent(event)
        self.picked_key.emit(self.picked[1] if self.picked else "")


@dataclass
class _Draft:
    """One text while the office is still working on it."""

    field: Field


class FieldEditor(QDialog):
    """«📐» — the blank, its texts, and every setting they have.

    Born for ТРУДАВОЙ, but any section may hand it its own ``catalogue``
    (key → picker label) and ``samples`` (key → drag-time preview); keys in
    ``frozen`` may be moved and styled but never deleted (a form's own
    printed values, the signature, the stamp).
    """

    def __init__(self, pages: list[bytes], fields: list[Field],
                 title: str = "Бланка", parent=None, *,
                 catalogue: dict[str, str] | None = None,
                 samples: dict[str, str] | None = None,
                 frozen: frozenset[str] | set[str] = frozenset(),
                 images: dict[str, bytes] | None = None,
                 pitches: dict[str, float] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{title} — матнларни қўйиш ва созлаш")
        self.setMinimumSize(1000, 820)
        self._cat = CATALOGUE if catalogue is None else catalogue
        self._samples = {} if samples is None else samples
        self._frozen = set(frozen)
        #: key → the real PNG shown in place of a word (печать, имзо)
        self._images = images or {}
        #: key → cell pitch (share of page width) for letter-cell rows
        self._pitches = pitches or {}

        self._pixmaps: list[QPixmap] = []
        for png in pages:
            pixmap = QPixmap()
            pixmap.loadFromData(png)
            self._pixmaps.append(pixmap)
        self._drafts = [_Draft(f) for f in fields]
        self._page = 1
        self._canvas: _PickCanvas | None = None
        self._filling = False

        outer = QVBoxLayout(self)
        hint = QLabel(
            "«➕ Матн» — бланкага янги матн қўшади ва у нимани англатишини "
            "рўйхатдан танлайсиз. Матнни босиб ушлаб суринг; ғилдирак ёки "
            "＋/－ — катта-кичик; ўқ тугмалари — аниқ суриш.\n"
            "Танланган матннинг ранги, қалинлиги ва шрифти шу ердан "
            "ўзгаради. Сақлаш — «OK».")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a94a3;")
        outer.addWidget(hint)

        nav = QHBoxLayout()
        nav.addWidget(QLabel("Саҳифа:"))
        self._pick_page = QComboBox()
        for number in range(1, len(self._pixmaps) + 1):
            self._pick_page.addItem(f"{number}-саҳифа", number)
        self._pick_page.currentIndexChanged.connect(self._on_page)
        nav.addWidget(self._pick_page)
        back = QPushButton("⬅ Олдинги")
        back.clicked.connect(lambda: self._step(-1))
        nav.addWidget(back)
        ahead = QPushButton("Кейингиси ➡")
        ahead.clicked.connect(lambda: self._step(+1))
        nav.addWidget(ahead)
        nav.addSpacing(16)
        add = QPushButton("➕ Матн")
        add.setToolTip("Янги матн қўшиш — маъносини рўйхатдан танлайсиз")
        add.clicked.connect(self._add)
        nav.addWidget(add)
        drop = QPushButton("🗑 Матн")
        drop.setToolTip("Танланган матнни ўчириш")
        drop.clicked.connect(self._drop)
        nav.addWidget(drop)
        nav.addStretch(1)
        outer.addLayout(nav)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Матн:"))
        self._pick_item = QComboBox()
        self._pick_item.currentIndexChanged.connect(self._on_item)
        bar.addWidget(self._pick_item, stretch=1)
        bigger = QPushButton("＋ катта")
        bigger.clicked.connect(lambda: self._canvas and
                               self._canvas.resize_picked(1))
        bar.addWidget(bigger)
        smaller = QPushButton("－ кичик")
        smaller.clicked.connect(lambda: self._canvas and
                                self._canvas.resize_picked(-1))
        bar.addWidget(smaller)
        outer.addLayout(bar)

        style = QHBoxLayout()
        self._colour = QPushButton("🎨 Ранг")
        self._colour.clicked.connect(self._set_colour)
        style.addWidget(self._colour)
        style.addWidget(QLabel("Қалинлик:"))
        self._weight = QComboBox()
        self._weight.addItems(WEIGHTS)
        self._weight.currentIndexChanged.connect(self._set_weight)
        style.addWidget(self._weight)
        style.addWidget(QLabel("Ҳолати:"))
        self._turn = QComboBox()
        for label, degrees in TURNS:
            self._turn.addItem(label, degrees)
        self._turn.setToolTip("Матн ётиб турадими ёки бланканинг четида "
                              "тик турадими")
        self._turn.currentIndexChanged.connect(self._set_turn)
        style.addWidget(self._turn)
        style.addWidget(QLabel("Шрифт:"))
        self._font = QComboBox()
        self._font.addItems(families())
        self._font.currentIndexChanged.connect(self._set_font)
        style.addWidget(self._font, stretch=1)
        outer.addLayout(style)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        outer.addWidget(self._scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self._show_page(1)

    # -------------------------------------------------------------- pages
    def _step(self, delta: int) -> None:
        index = self._pick_page.currentIndex() + delta
        if 0 <= index < self._pick_page.count():
            self._pick_page.setCurrentIndex(index)

    def _on_page(self, index: int) -> None:
        page = self._pick_page.itemData(index)
        if page is not None:
            self._show_page(page)

    def _on_this_page(self) -> list[int]:
        return [i for i, draft in enumerate(self._drafts)
                if draft.field.page == self._page]

    def _harvest(self) -> None:
        """Where the mouse left the texts of the page being left behind."""
        if self._canvas is None:
            return
        for tag, item in self._canvas.items.items():
            index = int(tag.rsplit("#", 1)[1])
            if 0 <= index < len(self._drafts):
                self._drafts[index].field = replace(
                    self._drafts[index].field, x=round(item.x, 5),
                    baseline=round(item.baseline, 5), size=round(item.size, 5))

    def _label_of(self, field: Field) -> str:
        return self._cat.get(field.key) or field.label()

    def _sample_of(self, field: Field) -> str:
        return self._samples.get(field.key) or field.sample()

    def _item_of(self, field: Field, tag: str) -> Item:
        return Item(key=tag, label=self._label_of(field),
                    sample=self._sample_of(field), x=field.x,
                    baseline=field.baseline, size=field.size,
                    colour=field.colour, font_family=field.font,
                    bold=field.bold, image=self._images.get(field.key),
                    pitch=self._pitches.get(field.key))

    def _show_page(self, page: int, keep: int | None = None) -> None:
        self._harvest()
        self._page = page
        mine = self._on_this_page()
        items = [self._item_of(self._drafts[i].field,
                               f"{self._drafts[i].field.key}#{i}")
                 for i in mine]
        canvas = _PickCanvas(self._pixmaps[page - 1], items, [])
        canvas.picked_key.connect(self._on_canvas_pick)
        self._canvas = canvas
        self._scroll.setWidget(canvas)

        self._filling = True
        self._pick_item.clear()
        for index in mine:
            field = self._drafts[index].field
            self._pick_item.addItem(self._label_of(field), index)
        self._filling = False
        if self._pick_item.count():
            wanted = self._pick_item.findData(keep if keep is not None
                                              else mine[0])
            self._pick_item.setCurrentIndex(max(0, wanted))
            self._on_item(self._pick_item.currentIndex())
        else:
            self._show_style(None)

    # -------------------------------------------------------------- texts
    def _picked(self) -> int | None:
        index = self._pick_item.currentData()
        return None if index is None else int(index)

    def _on_item(self, _index: int) -> None:
        if self._filling:
            return
        index = self._picked()
        if index is None or self._canvas is None:
            return
        self._canvas.pick("item", f"{self._drafts[index].field.key}#{index}")
        self._show_style(index)

    def _on_canvas_pick(self, tag: str) -> None:
        if not tag:
            return
        index = int(tag.rsplit("#", 1)[1])
        at = self._pick_item.findData(index)
        if at >= 0:
            self._filling = True
            self._pick_item.setCurrentIndex(at)
            self._filling = False
            self._show_style(index)

    def _show_style(self, index: int | None) -> None:
        """The bar always shows the picked text's own settings."""
        self._filling = True
        enabled = index is not None
        for widget in (self._colour, self._weight, self._turn, self._font):
            widget.setEnabled(enabled)
        if enabled:
            field = self._drafts[index].field
            self._weight.setCurrentIndex(1 if field.bold else 0)
            turned = self._turn.findData(getattr(field, "rotate", 0))
            self._turn.setCurrentIndex(turned if turned >= 0 else 0)
            at = self._font.findText(field.font)
            if at < 0:
                self._font.insertItem(0, field.font)
                at = 0
            self._font.setCurrentIndex(at)
            colour = QColor(*(int(c * 255) for c in field.colour))
            self._colour.setStyleSheet(
                f"background:{colour.name()};"
                f"color:{'#fff' if colour.lightness() < 140 else '#000'};")
        else:
            self._colour.setStyleSheet("")
        self._filling = False

    def _restyle(self, **change) -> None:
        index = self._picked()
        if index is None:
            return
        self._harvest()
        self._drafts[index].field = replace(self._drafts[index].field, **change)
        self._show_page(self._page, keep=index)

    def _set_colour(self) -> None:
        index = self._picked()
        if index is None:
            return
        now = QColor(*(int(c * 255) for c in self._drafts[index].field.colour))
        colour = QColorDialog.getColor(now, self, "Матн ранги")
        if colour.isValid():
            self._restyle(colour=(colour.redF(), colour.greenF(),
                                  colour.blueF()))

    def _set_weight(self, index: int) -> None:
        if not self._filling:
            self._restyle(bold=index == 1)

    def _set_turn(self, _index: int) -> None:
        if not self._filling:
            self._restyle(rotate=int(self._turn.currentData() or 0))

    def _set_font(self, _index: int) -> None:
        if not self._filling:
            self._restyle(font=self._font.currentText())

    def _add(self) -> None:
        offered = {k: v for k, v in self._cat.items() if k not in self._frozen}
        labels = list(offered.values())
        picked, ok = QInputDialog.getItem(
            self, "Матн маъноси", "Бу матн ишчининг қайси маълумоти?",
            labels, 0, False)
        if not ok:
            return
        key = [k for k, v in offered.items() if v == picked][0]
        model = self._drafts[self._picked()].field if self._picked() is not None \
            else None
        made = Field(key=key, page=self._page)
        if model is not None:                 # a new text joins its neighbours
            made = replace(made, size=model.size, font=model.font,
                           bold=model.bold, colour=model.colour,
                           x=model.x, baseline=min(0.98, model.baseline + 0.03))
        self._harvest()
        self._drafts.append(_Draft(made))
        self._show_page(self._page, keep=len(self._drafts) - 1)

    def _drop(self) -> None:
        index = self._picked()
        if index is None:
            return
        if self._drafts[index].field.key in self._frozen:
            return                      # a form's own value is never deleted
        self._harvest()
        self._drafts.pop(index)
        self._show_page(self._page)

    # ------------------------------------------------------------- result
    def fields(self) -> list[Field]:
        """Every text, as the office left it."""
        self._harvest()
        return [draft.field for draft in self._drafts]
