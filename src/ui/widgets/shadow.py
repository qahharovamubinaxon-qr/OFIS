"""A soft drop shadow for the card surfaces — the depth QSS cannot give.

Qt stylesheets have no ``box-shadow``, so a panel styled only in QSS sits flat
on the ground. A ``QGraphicsDropShadowEffect`` is the one way to lift it, and
it is what makes the difference between a coloured rectangle and a card that
looks like a sheet laid on the desk.

Kept deliberately soft and low: a large blur, a short downward offset, and a
translucent black that reads as real depth on the daylight theme and stays
subtle on the night one — the same effect works on both grounds because it is
the absence of light, not a colour of its own.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


def add_shadow(widget: QWidget, *, blur: int = 24, dy: int = 4,
               alpha: int = 55) -> None:
    """Lay a soft shadow under ``widget``. One effect per widget — the last
    call wins, which is exactly what a re-style wants."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setXOffset(0)
    effect.setYOffset(dy)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)
