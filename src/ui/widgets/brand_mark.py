"""The program's mark: a stamped sheet, «OFIS 24/7», and who made it.

Drawn rather than loaded from a file so it stays sharp on any screen, follows
the light and dark themes, and takes the colour of whichever section is open —
the same paper colour the rail and the RUN button carry (see
:mod:`src.ui.theme`).

The mark itself is what the program does: a sheet of paper with a round stamp
across its corner. Nothing else in the sidebar is a picture, so this one is
kept quiet — a line drawing at the weight of the text beside it.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class BrandMark(QWidget):
    """«OFIS 24/7 / by MUSTAFO», with the stamped-sheet mark beside it."""

    def __init__(self, accent: str = "#A8BEDC", ink: str = "#E8E6E3",
                 muted: str = "#8E8B96") -> None:
        super().__init__()
        self.setObjectName("brandMark")
        self.setFixedHeight(74)
        self._accent = QColor(accent)
        self._ink = QColor(ink)
        self._muted = QColor(muted)

    def set_palette(self, accent: str, ink: str, muted: str) -> None:
        """Repaint in the open section's colour, and this theme's inks."""
        self._accent, self._ink, self._muted = (
            QColor(accent), QColor(ink), QColor(muted))
        self.update()

    # ------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:                       # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        wordmark = QFont(self.font())
        wordmark.setPointSizeF(14.0)
        wordmark.setWeight(QFont.Weight.DemiBold)
        wordmark.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.2)

        byline = QFont(self.font())
        byline.setPointSizeF(7.5)
        byline.setWeight(QFont.Weight.Medium)
        byline.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.4)

        # the lockup is centred as a whole: mark, then the two lines
        painter.setFont(wordmark)
        ofis_w = painter.fontMetrics().horizontalAdvance("OFIS ")
        clock_w = painter.fontMetrics().horizontalAdvance("24/7")
        mark = 26.0
        total = mark + 11.0 + ofis_w + clock_w
        left = (self.width() - total) / 2.0
        middle = self.height() / 2.0

        self._sheet(painter, QRectF(left, middle - mark / 2.0, mark, mark))

        text_x = left + mark + 11.0
        painter.setPen(self._ink)
        painter.drawText(QPointF(text_x, middle + 1.0), "OFIS ")
        painter.setPen(self._accent)
        painter.drawText(QPointF(text_x + ofis_w, middle + 1.0), "24/7")

        painter.setFont(byline)
        painter.setPen(self._muted)
        painter.drawText(QPointF(text_x + 1.0, middle + 17.0), "by MUSTAFO")
        painter.end()

    def _sheet(self, painter: QPainter, box: QRectF) -> None:
        """A sheet of paper with a stamp struck across its lower corner."""
        pen = QPen(self._ink, 1.4)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        page = QRectF(box.left(), box.top(), box.width() * 0.74, box.height())
        painter.drawRoundedRect(page, 3.0, 3.0)

        rule = QPen(self._ink, 1.0)
        rule.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(rule)
        for i in (0.30, 0.46):
            y = page.top() + page.height() * i
            painter.drawLine(QPointF(page.left() + 4.0, y),
                             QPointF(page.right() - 4.0, y))

        stamp = QRectF(box.right() - box.width() * 0.52,
                       box.bottom() - box.height() * 0.52,
                       box.width() * 0.52, box.height() * 0.52)
        painter.setPen(QPen(self._accent, 1.6))
        painter.drawEllipse(stamp)
        painter.setPen(QPen(self._accent, 1.3, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        centre = stamp.center()
        painter.drawLine(centre, QPointF(centre.x(), centre.y() - stamp.height() * 0.27))
        painter.drawLine(centre, QPointF(centre.x() + stamp.width() * 0.20, centre.y()))
