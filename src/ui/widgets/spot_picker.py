"""Point at where a value should be printed, on a picture of the page itself.

The МВД «Отметка о подтверждении» box is large and every hostel's stamp sits
somewhere else inside it, so the operator marks the spot with the mouse against
that hostel's own page rather than describing it in numbers. The marked point
is the *centre* of the printed text, and the text is drawn where it will land,
so what is on screen is what comes out of the printer.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_BOX = QColor("#ff8c1a")
_MARK = QColor("#0a7d2e")
_GHOST = QColor(120, 130, 145, 150)


class PageSpotCanvas(QWidget):
    """The rendered page with a draggable text marker on it."""

    moved = Signal(float, float)          # in page points

    def __init__(self, spot, parent=None) -> None:
        super().__init__(parent)
        self._spot = spot
        self._page = QPixmap()
        self._page.loadFromData(spot.image.png)
        self.x, self.y = spot.x, spot.y
        self.setFixedSize(self._page.size())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

    # ------------------------------------------------------------- geometry
    def _to_px(self, x: float, y: float) -> QPoint:
        px, py = self._spot.image.to_pixels(x, y)
        return QPoint(round(px), round(py))

    def _text_rect(self, at: QPoint, metrics) -> QRect:
        """The date's own box, centred on ``at`` — that is where it prints.

        The metrics are the painter's, not the widget's: the marker is drawn
        bold, and measuring with the lighter face clipped the last characters.
        """
        width = metrics.horizontalAdvance(self._spot.sample)
        return QRect(at.x() - width // 2, at.y() - metrics.ascent(),
                     width, metrics.height())

    def set_point(self, x: float, y: float) -> None:
        self.x, self.y = x, y
        self.moved.emit(x, y)
        self.update()

    # --------------------------------------------------------------- events
    def mousePressEvent(self, event) -> None:
        self._take(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._take(event)

    def _take(self, event) -> None:
        pos = event.position().toPoint()
        x, y = self._spot.image.to_points(pos.x(), pos.y())
        self.set_point(round(x, 1), round(y, 1))

    def _print_font(self) -> QFont:
        """The date at the size it will actually print, scaled to the render."""
        image = self._spot.image
        font = QFont("Times New Roman")
        font.setBold(self._spot.bold)
        font.setPixelSize(max(6, round(self._spot.size * image.width_px
                                       / image.width_pt)))
        return font

    # -------------------------------------------------------------- drawing
    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._page)

        if self._spot.box:
            x0, y0, x1, y1 = self._spot.box
            top_left, bottom_right = self._to_px(x0, y0), self._to_px(x1, y1)
            pen = QPen(_BOX, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(QRect(top_left, bottom_right))

        painter.setFont(self._print_font())
        metrics = painter.fontMetrics()

        if not self.is_default():
            ghost = self._to_px(self._spot.default_x, self._spot.default_y)
            painter.setPen(QPen(_GHOST, 1))
            painter.drawText(self._text_rect(ghost, metrics),
                             int(Qt.AlignmentFlag.AlignCenter), self._spot.sample)

        at = self._to_px(self.x, self.y)
        rect = self._text_rect(at, metrics)
        painter.fillRect(rect.adjusted(-4, -2, 4, 2), QColor(255, 255, 255, 210))
        painter.setPen(QPen(_MARK, 2))
        painter.drawRect(rect.adjusted(-4, -2, 4, 2))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._spot.sample)
        painter.drawLine(at.x() - 9, at.y() + 3, at.x() + 9, at.y() + 3)
        painter.end()

    def is_default(self) -> bool:
        """True while the marker still sits where the form itself puts it."""
        return (abs(self.x - self._spot.default_x) < 0.05
                and abs(self.y - self._spot.default_y) < 0.05)


class SpotPickerDialog(QDialog):
    """Mark where the stay-start date goes; OK returns the point in points."""

    def __init__(self, spot, *, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._spot = spot

        outer = QVBoxLayout(self)
        hint = QLabel(
            "Sichqoncha bilan bosing yoki bosib turib suring — "
            "boshlanish sanasi shu joyga chiqadi.\n"
            "Sariq punktir — blankaning «Отметка о подтверждении» katagi.")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        self.canvas = PageSpotCanvas(spot)
        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(False)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(scroll, stretch=1)

        self._readout = QLabel()
        reset = QPushButton("Standart joyga qaytarish")
        reset.clicked.connect(self._reset)
        row = QHBoxLayout()
        row.addWidget(self._readout, stretch=1)
        row.addWidget(reset)
        outer.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.canvas.moved.connect(self._show_point)
        self._show_point(self.canvas.x, self.canvas.y)
        self.resize(min(spot.image.width_px + 90, 1100),
                    min(spot.image.height_px + 220, 900))
        self._scroll_to_box(scroll)

    def _scroll_to_box(self, scroll: QScrollArea) -> None:
        """Open on the box, not on the top of an A4 page."""
        target = self._spot.box[1] if self._spot.box else self._spot.default_y
        _px, py = self._spot.image.to_pixels(0, target)
        scroll.verticalScrollBar().setValue(max(0, int(py) - 60))

    def _reset(self) -> None:
        self.canvas.set_point(self._spot.default_x, self._spot.default_y)

    def _show_point(self, x: float, y: float) -> None:
        default = (abs(x - self._spot.default_x) < 0.05
                   and abs(y - self._spot.default_y) < 0.05)
        self._readout.setText(
            f"Joy: x={x:.1f}  y={y:.1f}" + ("  (standart)" if default else ""))

    def point(self) -> tuple[float, float] | None:
        """The marked spot, or ``None`` when it is the form's own."""
        if self.canvas.is_default():
            return None
        return (self.canvas.x, self.canvas.y)
