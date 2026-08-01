"""The worker signs with the mouse before the card is printed.

A plain white pad; the stroke goes down in ink — the same indigo the
sample card's owner signed in. What leaves the dialog is a transparent
PNG, so on the card only the ink itself lands over the paper.
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.pdf.alpinist_spec import INK_RGB

#: The pad keeps the card's signature spot's own proportions.
PAD_W, PAD_H = 560, 340
PEN_WIDTH = 4


class _Canvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(PAD_W, PAD_H)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.image = QImage(PAD_W, PAD_H, QImage.Format.Format_ARGB32)
        self.image.fill(Qt.GlobalColor.transparent)
        self.touched = False
        self._last: QPoint | None = None

    def clear(self) -> None:
        self.image.fill(Qt.GlobalColor.transparent)
        self.touched = False
        self.update()

    # ------------------------------------------------------------ drawing
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._last = event.position().toPoint()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        point = event.position().toPoint()
        if self._last is None:
            self._last = point
            return
        painter = QPainter(self.image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(*INK_RGB), PEN_WIDTH,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(self._last, point)
        painter.end()
        self._last = point
        self.touched = True
        self.update()

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802 - Qt override
        self._last = None

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("white"))
        painter.setPen(QColor("#b9c2cf"))
        painter.drawRect(0, 0, PAD_W - 1, PAD_H - 1)
        painter.drawImage(0, 0, self.image)
        painter.end()


class SignaturePad(QDialog):
    """Opens, takes the stroke, hands back the ink as PNG bytes."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ишчининг имзоси")
        root = QVBoxLayout(self)
        hint = QLabel("Ишчи сичқонча билан шу майдонга имзо қўяди:")
        root.addWidget(hint)
        self._canvas = _Canvas()
        root.addWidget(self._canvas)

        row = QHBoxLayout()
        clear = QPushButton("🧹 Тозалаш")
        clear.clicked.connect(self._canvas.clear)
        row.addWidget(clear)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        root.addLayout(row)

    def signature_png(self) -> bytes | None:
        """The drawn ink, cropped to its own bounds — None if never touched."""
        if not self._canvas.touched:
            return None
        image = self._canvas.image
        bounds = self._ink_bounds(image)
        if bounds is not None:
            image = image.copy(bounds)
        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        return bytes(buffer.data())

    @staticmethod
    def _ink_bounds(image: QImage):
        import numpy as np
        from PySide6.QtCore import QRect

        raw = image.convertToFormat(QImage.Format.Format_ARGB32)
        buf = np.frombuffer(raw.constBits(), dtype=np.uint8).reshape(
            raw.height(), raw.bytesPerLine())[:, : raw.width() * 4]
        alpha = buf.reshape(raw.height(), raw.width(), 4)[:, :, 3]
        ys, xs = np.nonzero(alpha > 0)
        if len(xs) == 0:
            return None
        pad = PEN_WIDTH
        x0 = max(0, int(xs.min()) - pad)
        y0 = max(0, int(ys.min()) - pad)
        x1 = min(raw.width() - 1, int(xs.max()) + pad)
        y1 = min(raw.height() - 1, int(ys.max()) + pad)
        return QRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
