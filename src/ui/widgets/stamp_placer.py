"""Put a firm's stamp on its card with the mouse, against the card itself.

The office asked for exactly this: drag the stamp to where it goes, pull its
corner to make it bigger or smaller, and have it stay there — so that picking
that firm's stamp next time drops it in the same place at the same size.

What is on screen is what comes out of the printer: the blank is rendered at the
size it will print, the stamp is drawn over it at the size it will print, and
the place is kept as fractions of the page so it survives a firm re-scanning its
blank at another resolution.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
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

_FRAME = QColor("#ff8c1a")
_HANDLE = QColor("#0a7d2e")
#: How big the corner grip is, on screen.
_GRIP = 14
#: A stamp may never be smaller than this share of the page, or it is lost.
_MIN_SHARE = 0.03


class StampCanvas(QWidget):
    """The card with the stamp on it, draggable and resizable."""

    def __init__(self, page: QPixmap, stamp: QPixmap, box, parent=None) -> None:
        super().__init__(parent)
        self._page = page
        self._stamp = stamp
        self.box = list(box)                  # left, top, right, bottom (0..1)
        self._drag: str | None = None
        self._grab = QPoint()
        self.setMinimumSize(page.size())
        self.setMouseTracking(True)

    # -- geometry ------------------------------------------------------
    def _rect(self) -> QRect:
        w, h = self._page.width(), self._page.height()
        return QRect(int(self.box[0] * w), int(self.box[1] * h),
                     max(1, int((self.box[2] - self.box[0]) * w)),
                     max(1, int((self.box[3] - self.box[1]) * h)))

    def _set_rect(self, rect: QRect) -> None:
        w, h = self._page.width(), self._page.height()
        left = max(0.0, min(rect.left() / w, 1.0 - _MIN_SHARE))
        top = max(0.0, min(rect.top() / h, 1.0 - _MIN_SHARE))
        right = min(1.0, max(rect.right() / w, left + _MIN_SHARE))
        bottom = min(1.0, max(rect.bottom() / h, top + _MIN_SHARE))
        self.box = [left, top, right, bottom]
        self.update()

    # -- painting ------------------------------------------------------
    def paintEvent(self, event) -> None:      # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._page)
        rect = self._rect()
        if not self._stamp.isNull():
            painter.setOpacity(0.9)
            painter.drawPixmap(rect, self._stamp)
            painter.setOpacity(1.0)
        pen = QPen(_FRAME, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(rect)
        painter.fillRect(QRect(rect.right() - _GRIP, rect.bottom() - _GRIP,
                               _GRIP, _GRIP), _HANDLE)
        painter.end()

    # -- mouse ---------------------------------------------------------
    def _on_grip(self, point: QPoint) -> bool:
        rect = self._rect()
        return QRect(rect.right() - _GRIP, rect.bottom() - _GRIP,
                     _GRIP, _GRIP).contains(point)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        point = event.position().toPoint()
        if self._on_grip(point):
            self._drag = "size"
        elif self._rect().contains(point):
            self._drag = "move"
            self._grab = point - self._rect().topLeft()

    def mouseMoveEvent(self, event) -> None:   # noqa: N802 - Qt override
        point = event.position().toPoint()
        if self._drag is None:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._on_grip(point)
                           else (Qt.CursorShape.OpenHandCursor
                                 if self._rect().contains(point)
                                 else Qt.CursorShape.ArrowCursor))
            return
        rect = self._rect()
        if self._drag == "size":
            # the corner follows the mouse; the stamp keeps its own proportions
            width = max(_GRIP, point.x() - rect.left())
            ratio = (self._stamp.height() / self._stamp.width()
                     if not self._stamp.isNull() and self._stamp.width() else 1.0)
            self._set_rect(QRect(rect.left(), rect.top(),
                                 width, max(_GRIP, int(width * ratio))))
        else:
            top_left = point - self._grab
            self._set_rect(QRect(top_left, rect.size()))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._drag = None


class StampPlacer(QDialog):
    """«Печатни жойлаш» — drag it where it goes, pull the corner to size it."""

    def __init__(self, page_png: bytes, stamp_png: bytes, box, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Печатни жойлаш — сичқонча билан суринг")
        self.setMinimumSize(760, 720)

        page = QPixmap()
        page.loadFromData(page_png)
        stamp = QPixmap()
        stamp.loadFromData(stamp_png)
        self._canvas = StampCanvas(page, stamp, box)

        outer = QVBoxLayout(self)
        hint = QLabel(
            "Печатни ушлаб суринг — жойи ўзгаради. Ўнг пастки бурчагидаги "
            "яшил квадратни тортинг — катта-кичик бўлади.\n"
            "Сақлангач, шу фирманинг печати ҳар сафар шу жойга, шу ўлчамда "
            "тушади.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a94a3;")
        outer.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidget(self._canvas)
        scroll.setWidgetResizable(False)
        outer.addWidget(scroll, stretch=1)

        row = QHBoxLayout()
        reset = QPushButton("↺ Бошланғич жой")
        reset.clicked.connect(self._reset)
        row.addWidget(reset)
        row.addStretch(1)
        outer.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _reset(self) -> None:
        from src.pdf.mig_spec import DEFAULT_STAMP

        self._canvas.box = list(DEFAULT_STAMP)
        self._canvas.update()

    def box(self) -> tuple[float, float, float, float]:
        return tuple(self._canvas.box)       # type: ignore[return-value]
