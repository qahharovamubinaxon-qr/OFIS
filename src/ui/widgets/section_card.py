"""One section, as a card on the home screen.

The office does not look for a section by reading forty names down a list —
they look for the colour of the paper it prints and the shape of its icon, the
way they reach into their own stack of blanks. So the card carries the
section's own colour (:mod:`src.ui.theme`), its icon, and the one number that
says whether it has been used today.

Painted rather than styled: the cut corner has no stylesheet equivalent (see
:mod:`src.ui.widgets.chamfer`), and a real :class:`QAbstractButton` underneath
keeps the keyboard working — Tab reaches it, Space and Enter open it, which a
clickable ``QFrame`` would quietly take away.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QWidget

from src.ui.sections import Section
from src.ui.widgets.chamfer import CUT, chamfer_path


@dataclass(frozen=True)
class CardInk:
    """The inks a card is drawn with — everything except its own colour."""

    panel: str
    panel_hover: str
    line: str
    ink: str
    muted: str
    machine: str


#: The night ground's inks. The home screen hands the daylight ones in.
NIGHT = CardInk(panel="#0A0E14", panel_hover="#0E141C", line="#26384A",
                ink="#E8EEF2", muted="#60707E", machine="#FF7A18")
DAY = CardInk(panel="#FFFFFF", panel_hover="#F4F8FA", line="#C9D6DD",
              ink="#10212B", muted="#6B8291", machine="#B4530A")


class SectionCard(QAbstractButton):
    """A section the operator can open, in the colour of what it prints."""

    chosen = Signal(str)

    def __init__(self, section: Section, colour: str, ink: CardInk = NIGHT,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sectionCard")
        self.section = section
        self._colour = QColor(colour)
        self._ink = ink
        self._count: int | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(190, 96)
        self.setToolTip(f"{section.title} — {section.subtitle}")
        self.setAccessibleName(section.title)
        self.clicked.connect(lambda: self.chosen.emit(self.section.key))

    def sizeHint(self) -> QSize:                               # noqa: N802
        return QSize(236, 96)

    # -------------------------------------------------------------- state
    def set_count(self, count: int | None) -> None:
        """How many documents this section made today. ``None`` prints nothing
        — a section whose work is not counted must not show a false zero."""
        self._count = count
        self.update()

    def set_ink(self, ink: CardInk) -> None:
        self._ink = ink
        self.update()

    def set_colour(self, colour: str) -> None:
        self._colour = QColor(colour)
        self.update()

    # ----------------------------------------------------------- painting
    def paintEvent(self, event) -> None:                       # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        lit = self.underMouse() or self.hasFocus() or self.isDown()
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = chamfer_path(box, CUT)

        painter.fillPath(path, QColor(self._ink.panel_hover if lit
                                      else self._ink.panel))
        edge = QColor(self._colour) if lit else QColor(self._ink.line)
        painter.strokePath(path, QPen(edge, 1.0))

        pad = 16.0
        self._paint_head(painter, pad, lit)
        self._paint_rule(painter, pad, lit)
        self._paint_foot(painter, pad, lit)

    def _paint_head(self, painter: QPainter, pad: float, lit: bool) -> None:
        icon = QFont(self.font())
        icon.setPointSizeF(13.0)
        painter.setFont(icon)
        painter.setPen(self._colour)
        icon_w = QFontMetricsF(icon).horizontalAdvance(self.section.icon)
        painter.drawText(QRectF(pad, 14.0, icon_w + 4.0, 22.0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self.section.icon)

        name = QFont(self.font())
        name.setPointSizeF(10.0)
        name.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name)
        painter.setPen(QColor("#FFFFFF") if lit else QColor(self._ink.ink))
        left = pad + icon_w + 10.0
        room = self.width() - left - pad
        text = QFontMetricsF(name).elidedText(
            self.section.title, Qt.TextElideMode.ElideRight, room)
        painter.drawText(QRectF(left, 14.0, room, 22.0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         text)

    def _paint_rule(self, painter: QPainter, pad: float, lit: bool) -> None:
        """The dashed bar in the section's colour — the card's paper stripe."""
        colour = QColor(self._colour)
        if not lit:
            colour.setAlpha(150)
        y = 46.0
        x = pad
        end = self.width() - pad
        while x < end:
            painter.fillRect(QRectF(x, y, min(7.0, end - x), 3.0), colour)
            x += 11.0

    def _paint_foot(self, painter: QPainter, pad: float, lit: bool) -> None:
        """The line under the stripe: today's count where the program really
        knows it, and otherwise what the section does.

        The archive records which company a document was made for, not which
        section made it, so most sections have no honest count — and «БУГУН ·
        0» under every one of them would be a number the office could not
        trust. The subtitle is true, and it is what a new operator needs.
        """
        small = QFont(self.font())
        small.setPointSizeF(7.5)
        if self._count is None:
            text = self.section.subtitle
            painter.setPen(QColor(self._ink.muted))
        else:
            text = f"БУГУН · {self._count}"
            small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
            painter.setPen(QColor(self._colour) if lit
                           else QColor(self._ink.muted))
        painter.setFont(small)
        room = self.width() - 2 * pad - (14.0 if lit else 0.0)
        painter.drawText(QRectF(pad, self.height() - 34.0, room, 24.0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         QFontMetricsF(small).elidedText(
                             text, Qt.TextElideMode.ElideRight, room))

        if lit:
            chevron = QPen(QColor(self._ink.machine), 2.0)
            chevron.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(chevron)
            right = self.width() - pad - 10.0
            middle = self.height() - 22.0
            painter.drawLine(QRectF(right, middle - 4, 0, 0).topLeft(),
                             QRectF(right + 4, middle, 0, 0).topLeft())
            painter.drawLine(QRectF(right + 4, middle, 0, 0).topLeft(),
                             QRectF(right, middle + 4, 0, 0).topLeft())
