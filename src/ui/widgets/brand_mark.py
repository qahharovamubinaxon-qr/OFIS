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
        """A sheet of paper with a stamp struck across its lower corner.

        Same proportions as the app icon (``scripts/make_icon.py``) so the mark
        on the taskbar and the mark in the sidebar are one thing. The icon is
        filled; this one is a line drawing, because at 26 px beside body text a
        solid shape would shout. The icon's inner ring is dropped for the same
        reason — at this size it would close up into a blob.
        """
        pen = QPen(self._ink, 1.4)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        page = QRectF(box.left(), box.top(),
                      box.width() * 0.70, box.height() * 0.90)
        painter.drawRoundedRect(page, 2.6, 2.6)

        rule = QPen(self._ink, 1.0)
        rule.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(rule)
        inset = page.width() * 0.17
        for share, length in ((0.20, 0.66), (0.36, 0.66), (0.52, 0.40)):
            y = page.top() + page.height() * share
            painter.drawLine(QPointF(page.left() + inset, y),
                             QPointF(page.left() + inset + page.width() * length, y))

        size = box.width() * 0.58
        centre = QPointF(box.left() + box.width() * 0.64, box.bottom() - size / 2.0)
        stamp = QRectF(centre.x() - size / 2.0, centre.y() - size / 2.0, size, size)
        painter.setPen(QPen(self._accent, 1.6))
        painter.drawEllipse(stamp)

        # the stamp's face is a clock — the «24/7» beside it, drawn
        painter.setPen(QPen(self._accent, 1.3, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        painter.drawLine(centre, QPointF(centre.x(), centre.y() - size * 0.28))
        painter.drawLine(centre, QPointF(centre.x() + size * 0.21, centre.y()))
