"""Arrange a form's printed values on the blank itself, with the mouse.

Every office and every firm hands over its own scan of a form, and no two are
typed quite alike. Rather than the office editing numbers in a file — and
rebuilding the program each time — it drags each value into place against its
own blank and saves. What it arranges is kept beside that blank, so one firm's
form is never moved by arranging another's.

On screen is what comes out of the printer: the blank is drawn at the size it
prints and every value in the face and size it will be printed in.

This widget knows nothing about any one section. A section hands it a picture of
the page and a list of :class:`Item` (and :class:`RuleItem` for the lines some
forms underline with), and gets back where everything ended up — all in
FRACTIONS of the page, so a firm re-scanning its blank at another resolution
changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_PICKED = QColor("#ff8c1a")
_GHOST = QColor(120, 130, 145, 110)
_RULE = QColor("#0a7d2e")

#: One step of the arrow keys, as a share of the page — about a fifth of a
#: millimetre on A4, which is as fine as anyone needs.
NUDGE_X = 0.0004
NUDGE_Y = 0.0003
#: One notch of the wheel, as a share of the page height — about a point.
SIZE_STEP = 0.0012

#: How far the page itself may be magnified. Out to a half for a whole A4 on
#: a small screen, in to four times for lining a value up on a printed rule.
MIN_ZOOM, MAX_ZOOM = 0.5, 4.0
#: What one press of ＋ / － does.
ZOOM_STEP = 0.25


@dataclass
class Item:
    """One printed value: what it is, and where it goes on the page."""

    key: str
    label: str
    #: what to show in its place while arranging
    sample: str
    x: float
    baseline: float
    #: type size, as a share of the page HEIGHT
    size: float
    colour: tuple[float, float, float] = (0.08, 0.08, 0.08)
    font_family: str = "Courier New"
    #: shown as it prints — a section that never sets it is unaffected
    bold: bool = False
    #: a PICTURE item (the real печать/имзо, not a word standing in for
    #: it): the PNG itself; ``size`` is its height, width follows the
    #: picture's own shape
    image: bytes | None = None
    #: a letter-cell row: distance between cell centres as a share of the
    #: page WIDTH; ``x`` is then the FIRST CELL'S CENTRE and every letter
    #: is drawn in its own cell — exactly the way it prints
    pitch: float | None = None


@dataclass
class RuleItem:
    """A line the form draws under something — corner to corner of a word."""

    key: str
    label: str
    x0: float
    x1: float
    y: float


@dataclass
class Result:
    """Where everything ended up, ready to be written beside the blank."""

    items: dict[str, list[float]] = field(default_factory=dict)
    rules: dict[str, list[float]] = field(default_factory=dict)


class _Canvas(QWidget):
    def __init__(self, page: QPixmap, items: list[Item],
                 rules: list[RuleItem], parent=None) -> None:
        super().__init__(parent)
        #: The page as it arrived. Zooming never touches it, so no amount of
        #: zooming in and out slowly degrades the picture.
        self._source = page
        self._page = page
        self._zoom = 1.0
        self.items = {i.key: i for i in items}
        self.order = [i.key for i in items]
        self.rules = {r.key: r for r in rules}
        self.rule_order = [r.key for r in rules]
        self.picked: tuple[str, str] | None = None
        self._grab = QPoint()
        self._pixmaps: dict[str, QPixmap] = {}
        self.setMinimumSize(page.size())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # -- zoom ----------------------------------------------------------
    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, factor: float) -> None:
        """Draw the page larger or smaller — and everything on it with it.

        Every position, size and mouse test in this widget is a FRACTION of
        the page, so scaling the page alone scales the whole scene and the
        arithmetic stays true. What is saved is fractions, which is why the
        office may zoom as it likes and the result is identical.
        """
        factor = max(MIN_ZOOM, min(MAX_ZOOM, float(factor)))
        if abs(factor - self._zoom) < 1e-6:
            return
        self._zoom = factor
        self._page = (self._source if factor == 1.0 else self._source.scaled(
            max(1, round(self._source.width() * factor)),
            max(1, round(self._source.height() * factor)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        self.setMinimumSize(self._page.size())
        self.resize(self._page.size())
        self.update()

    # -- geometry ------------------------------------------------------
    def _font(self, item: Item) -> QFont:
        font = QFont(item.font_family)
        font.setPixelSize(max(4, round(item.size * self._page.height())))
        font.setBold(item.bold)
        return font

    def _pixmap_of(self, item: Item) -> QPixmap | None:
        cached = self._pixmaps.get(item.key)
        if cached is None and item.image:
            cached = QPixmap()
            cached.loadFromData(item.image)
            self._pixmaps[item.key] = cached
        return cached

    def _rect_of(self, item: Item) -> QRect:
        left = round(item.x * self._page.width())
        bottom = round(item.baseline * self._page.height())
        picture = self._pixmap_of(item)
        if picture is not None and picture.height():
            height = max(6, round(item.size * self._page.height()))
            width = max(6, round(height * picture.width() / picture.height()))
            return QRect(left, bottom - height, width, height)
        metrics = QFontMetrics(self._font(item))
        if item.pitch:
            # letters live in cells: from half a cell left of the first
            # cell's centre to half a cell right of the last one's
            pitch = item.pitch * self._page.width()
            count = max(1, len(item.sample))
            return QRect(round(left - pitch / 2), bottom - metrics.ascent(),
                         round(pitch * count),
                         metrics.ascent() + metrics.descent())
        return QRect(left, bottom - metrics.ascent(),
                     max(6, metrics.horizontalAdvance(item.sample)),
                     metrics.ascent() + metrics.descent())

    # -- painting ------------------------------------------------------
    def paintEvent(self, event) -> None:      # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._page)
        for key in self.order:
            item = self.items[key]
            rect = self._rect_of(item)
            chosen = self.picked == ("item", key)
            picture = self._pixmap_of(item)
            baseline = round(item.baseline * self._page.height())
            if picture is not None:
                painter.drawPixmap(rect, picture)
            else:
                painter.setFont(self._font(item))
                painter.setPen(QPen(QColor(*(int(c * 255)
                                             for c in item.colour))))
                if item.pitch:
                    metrics = QFontMetrics(self._font(item))
                    pitch = item.pitch * self._page.width()
                    for i, ch in enumerate(item.sample):
                        cx = item.x * self._page.width() + i * pitch
                        painter.drawText(
                            QPoint(round(cx - metrics.horizontalAdvance(ch)
                                         / 2), baseline), ch)
                else:
                    painter.drawText(QPoint(rect.left(), baseline),
                                     item.sample)
            painter.setPen(QPen(_PICKED if chosen else _GHOST,
                                2 if chosen else 1, Qt.PenStyle.DashLine))
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))
        for key in self.rule_order:
            rule = self.rules[key]
            chosen = self.picked == ("rule", key)
            painter.setPen(QPen(_PICKED if chosen else _RULE, 3 if chosen else 2))
            top = round(rule.y * self._page.height())
            painter.drawLine(round(rule.x0 * self._page.width()), top,
                             round(rule.x1 * self._page.width()), top)
        painter.end()

    # -- picking -------------------------------------------------------
    def _hit(self, point: QPoint):
        for key in reversed(self.order):
            if self._rect_of(self.items[key]).adjusted(-3, -3, 3, 3).contains(point):
                return ("item", key)
        for key in self.rule_order:
            rule = self.rules[key]
            top = round(rule.y * self._page.height())
            if (abs(point.y() - top) <= 6
                    and round(rule.x0 * self._page.width()) - 6 <= point.x()
                    <= round(rule.x1 * self._page.width()) + 6):
                return ("rule", key)
        return None

    def pick(self, kind: str, key: str) -> None:
        self.picked = (kind, key)
        self.setFocus()
        self.update()

    # -- mouse & keys --------------------------------------------------
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        point = event.position().toPoint()
        self.picked = self._hit(point)
        self._grab = point
        self.setFocus()
        self.update()

    def mouseMoveEvent(self, event) -> None:   # noqa: N802 - Qt override
        if self.picked is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        point = event.position().toPoint()
        self.move_picked((point.x() - self._grab.x()) / self._page.width(),
                         (point.y() - self._grab.y()) / self._page.height())
        self._grab = point

    def wheelEvent(self, event) -> None:       # noqa: N802 - Qt override
        if self.picked is not None:
            self.resize_picked(1 if event.angleDelta().y() > 0 else -1)

    def keyPressEvent(self, event) -> None:    # noqa: N802 - Qt override
        steps = {Qt.Key.Key_Left: (-NUDGE_X, 0.0), Qt.Key.Key_Right: (NUDGE_X, 0.0),
                 Qt.Key.Key_Up: (0.0, -NUDGE_Y), Qt.Key.Key_Down: (0.0, NUDGE_Y)}
        if event.key() in steps and self.picked is not None:
            self.move_picked(*steps[event.key()])
        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.resize_picked(1)
        elif event.key() == Qt.Key.Key_Minus:
            self.resize_picked(-1)

    # -- moving --------------------------------------------------------
    def move_picked(self, dx: float, dy: float) -> None:
        if self.picked is None:
            return
        kind, key = self.picked
        if kind == "rule":
            rule = self.rules[key]
            rule.x0 = max(0.0, rule.x0 + dx)
            rule.x1 = min(1.0, rule.x1 + dx)
            rule.y = min(1.0, max(0.0, rule.y + dy))
        else:
            item = self.items[key]
            item.x = min(1.0, max(0.0, item.x + dx))
            item.baseline = min(1.0, max(0.0, item.baseline + dy))
        self.update()

    def resize_picked(self, direction: int) -> None:
        if self.picked is None:
            return
        kind, key = self.picked
        if kind == "rule":
            # a line has no type size; the wheel stretches its RIGHT end
            rule = self.rules[key]
            rule.x1 = min(1.0, max(rule.x0 + 0.01, rule.x1 + 0.004 * direction))
        else:
            item = self.items[key]
            item.size = max(0.004, item.size + SIZE_STEP * direction)
        self.update()


class LayoutEditor(QDialog):
    """«Матнларни жойлаш» — drag each value where this blank wants it."""

    def __init__(self, page_png: bytes, items: list[Item],
                 rules: list[RuleItem] | None = None,
                 title: str = "Матнларни жойлаш", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{title} — сичқонча билан суринг")
        self.setMinimumSize(900, 780)

        page = QPixmap()
        page.loadFromData(page_png)
        self._canvas = _Canvas(page, items, list(rules or ()))

        outer = QVBoxLayout(self)
        hint = QLabel(
            "Матнни босиб ушланг ва суринг — жойи ўзгаради.\n"
            "Танланганини КАТТА-КИЧИК қилиш: сичқонча ғилдираги, ёки ＋ / －.\n"
            "Аниқ суриш: ўқ тугмалари (←↑↓→).\n"
            "Сақлангач, бу бланкага босиладиган ҳар бир ҳужжат шу жойларга "
            "тушади.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a94a3;")
        outer.addWidget(hint)

        picker = QHBoxLayout()
        picker.addWidget(QLabel("Танлаш:"))
        self._pick = QComboBox()
        for item in items:
            self._pick.addItem(item.label, ("item", item.key))
        for rule in (rules or ()):
            self._pick.addItem(f"чизиқ: {rule.label}", ("rule", rule.key))
        self._pick.currentIndexChanged.connect(self._on_pick)
        picker.addWidget(self._pick, stretch=1)
        bigger = QPushButton("＋ катта")
        bigger.clicked.connect(lambda: self._canvas.resize_picked(1))
        picker.addWidget(bigger)
        smaller = QPushButton("－ кичик")
        smaller.clicked.connect(lambda: self._canvas.resize_picked(-1))
        picker.addWidget(smaller)
        outer.addLayout(picker)

        scroll = QScrollArea()
        scroll.setWidget(self._canvas)
        scroll.setWidgetResizable(False)
        outer.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _on_pick(self) -> None:
        kind, key = self._pick.currentData()
        self._canvas.pick(kind, key)

    def result(self) -> Result:
        """Where everything ended up, in page fractions."""
        return Result(
            items={k: [round(i.x, 5), round(i.baseline, 5), round(i.size, 5)]
                   for k, i in self._canvas.items.items()},
            rules={k: [round(r.x0, 5), round(r.x1, 5), round(r.y, 5)]
                   for k, r in self._canvas.rules.items()})
