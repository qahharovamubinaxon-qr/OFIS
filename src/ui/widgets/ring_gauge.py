"""A ring with the number inside it — the program's one way of showing how far
along something is.

A bar tells you a job is running; a ring tells you how much of it is left
while keeping the number itself readable at a glance across the room, which is
how the office actually watches a document being made. The same widget serves
the home screen's counters (how many documents today, how much of the month's
block of numbers is used) and the progress of a single run.

Two things are kept apart on purpose:

* **how full the ring is** — ``set_progress(0…1)``
* **what the middle says** — ``set_centre("12")`` or ``set_centre("72", "%")``

A count of 12 documents does not fill a ring to 12 % of anything, and a
percentage is not always a count. Tying the two together would force one of
them to lie.

Qt stylesheets cannot draw an arc, so this paints itself, and takes its
colours from :mod:`src.ui.theme` like the rest of the window.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

#: Qt measures arcs in sixteenths of a degree, from three o'clock, anticlockwise.
_SIXTEENTHS = 16
_FULL_CIRCLE = 360
_TWELVE_OCLOCK = 90 * _SIXTEENTHS


class RingGauge(QWidget):
    """A progress ring with its reading in the middle."""

    def __init__(
        self,
        *,
        caption: str = "",
        diameter: int = 78,
        thickness: int = 7,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ringGauge")
        self._progress = 0.0
        self._centre = ""
        self._suffix = ""
        self._caption = caption
        self._thickness = max(2, int(thickness))
        self._arc = QColor("#FF7A18")
        self._track = QColor("#1C2733")
        self._ink = QColor("#E8EEF2")
        self._muted = QColor("#60707E")
        self._start = 0.0
        self.setFixedSize(int(diameter), int(diameter))

    def set_start_angle(self, degrees: float) -> None:
        """Where the arc begins, in degrees clockwise from twelve o'clock.

        A gauge starts at the top and stays there. A *sweep* — the ring that
        says «something is happening» while nobody can say how much of it is
        done — is the same arc walked around the dial, and this is what walks
        it.
        """
        self._start = float(degrees) % 360.0
        self.update()

    # ------------------------------------------------------------- reading
    def set_progress(self, progress: float) -> None:
        """How much of the ring is drawn, 0…1. Values outside are clamped —
        a count that overshoots its target must not wrap the arc around."""
        value = 0.0 if progress != progress else float(progress)  # NaN → 0
        self._progress = min(1.0, max(0.0, value))
        self.update()

    def set_centre(self, text: str, suffix: str = "") -> None:
        """What is written in the middle: the number, and a small unit after it."""
        self._centre, self._suffix = str(text), str(suffix)
        self.update()

    def set_fraction(self, done: float, total: float) -> None:
        """Fill the ring by ``done`` out of ``total`` and write the percent.

        A total of zero means there is nothing to be a part of: the ring stays
        empty and the middle says «—» rather than dividing by zero or claiming
        100 %.
        """
        if total <= 0:
            self.set_progress(0.0)
            self.set_centre("—")
            return
        share = done / total
        self.set_progress(share)
        self.set_centre(str(int(round(share * 100))), "%")

    def progress(self) -> float:
        return self._progress

    def centre_text(self) -> str:
        return self._centre

    def span_degrees(self) -> float:
        """The arc actually drawn, in degrees — the one number worth testing."""
        return self._progress * _FULL_CIRCLE

    # ------------------------------------------------------------- colours
    def set_colours(self, arc: str, track: str, ink: str, muted: str) -> None:
        self._arc, self._track = QColor(arc), QColor(track)
        self._ink, self._muted = QColor(ink), QColor(muted)
        self.update()

    def set_caption(self, caption: str) -> None:
        self._caption = str(caption)
        self.update()

    # ------------------------------------------------------------ painting
    def paintEvent(self, event) -> None:                       # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pad = self._thickness / 2.0 + 1.0
        box = QRectF(pad, pad, self.width() - 2 * pad, self.height() - 2 * pad)

        track = QPen(self._track, self._thickness)
        track.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(track)
        painter.drawEllipse(box)

        if self._progress > 0:
            arc = QPen(self._arc, self._thickness)
            arc.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(arc)
            # clockwise from twelve o'clock: the direction a clock hand and a
            # filling gauge both move, so it reads as time passing
            span = -int(round(self.span_degrees() * _SIXTEENTHS))
            begin = _TWELVE_OCLOCK - int(round(self._start * _SIXTEENTHS))
            painter.drawArc(box, begin, span)

        self._paint_centre(painter)

    def _paint_centre(self, painter: QPainter) -> None:
        if not self._centre:
            return
        number = QFont(self.font())
        number.setPointSizeF(max(9.0, self.height() * 0.235))
        number.setWeight(QFont.Weight.DemiBold)
        painter.setFont(number)
        painter.setPen(self._ink)

        metrics = painter.fontMetrics()
        number_w = metrics.horizontalAdvance(self._centre)

        unit = QFont(self.font())
        unit.setPointSizeF(max(6.0, self.height() * 0.105))
        unit_w = 0.0
        if self._suffix:
            painter.setFont(unit)
            unit_w = painter.fontMetrics().horizontalAdvance(self._suffix) + 2.0
            painter.setFont(number)

        left = (self.width() - number_w - unit_w) / 2.0
        baseline = self.height() / 2.0 + metrics.capHeight() / 2.0
        if self._caption:
            baseline -= self.height() * 0.07
        painter.drawText(QRectF(left, baseline - metrics.ascent(),
                                number_w, metrics.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self._centre)

        if self._suffix:
            painter.setFont(unit)
            painter.setPen(self._arc)
            painter.drawText(QRectF(left + number_w + 2.0,
                                    baseline - metrics.ascent(),
                                    unit_w, metrics.height()),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             self._suffix)

        if self._caption:
            small = QFont(self.font())
            small.setPointSizeF(max(5.5, self.height() * 0.085))
            small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
            painter.setFont(small)
            painter.setPen(self._muted)
            painter.drawText(QRectF(0, self.height() / 2.0 + self.height() * 0.10,
                                    self.width(), self.height() * 0.22),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             self._caption)
