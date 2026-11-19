"""A framed block inside a screen — the card the HUD is built from.

The home screen is cards; the inside of a section had stayed a flat sheet of
boxes, so the program changed language halfway through. This is the piece
that makes the two agree: one hairline frame, a square corner, and a small
machine-coloured heading that says what the block is for.

It is deliberately thinner than :class:`src.ui.widgets.card.Card`, which is
the Settings screen's building block and carries a shadow and a two-line
head. Inside a working section the block has to disappear behind the work —
a frame and a heading, nothing more.

Everything it looks like comes from the stylesheet (``#card``, ``#fieldLabel``),
so a section wrapped in panels follows the theme and the day/night switch
without knowing anything about either.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QLayout, QVBoxLayout, QWidget


class Panel(QWidget):
    """A titled frame to put a block of a screen inside."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        # a plain QWidget ignores the stylesheet's background and border
        # without this — the frame simply would not be drawn
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 16)
        outer.setSpacing(10)
        if title:
            head = QLabel(title.upper())
            head.setObjectName("fieldLabel")
            outer.addWidget(head)
        self._body = outer

    def add(self, item: QWidget | QLayout, stretch: int = 0) -> None:
        """Put a widget or a whole layout inside the frame."""
        if isinstance(item, QWidget):
            self._body.addWidget(item, stretch)
        else:
            self._body.addLayout(item, stretch)

    def grid(self, *, spacing: int = 10, columns: int = 16) -> QGridLayout:
        """A grid laid out inside the frame — the usual block of boxes."""
        grid = QGridLayout()
        grid.setVerticalSpacing(spacing)
        grid.setHorizontalSpacing(columns)
        grid.setContentsMargins(0, 0, 0, 0)
        self._body.addLayout(grid)
        return grid


def panelled(title: str, item: QWidget | QLayout) -> Panel:
    """``item``, framed and titled — the one-liner a view uses while building."""
    panel = Panel(title)
    panel.add(item)
    return panel
