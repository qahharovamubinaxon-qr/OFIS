"""Every screen scrolls when the window is shorter than the work on it.

A dense section — МИГ, МВД ТРУДАВОЙ, ПЕРЕВОД — is a page of boxes, and a
laptop screen is not always tall enough to hold one. Without somewhere to
scroll, Qt squeezes the rows until the text boxes climb on top of their own
labels, which is exactly what the office photographed: «ФАМИЛИЯ:» with the
surname printed across it, unreadable.

So the shell hangs each screen inside this: the screen keeps the height it
actually needs, and anything past the window's edge is reached by scrolling —
the one behaviour that cannot fail, however small the monitor or however many
boxes a section grows next year.

The scroll host stands between the window's stack and the screen, so the two
things the shell asks of a screen — ``refresh()`` and ``reset()`` — would
land on the wrapper instead. :attr:`view` is how the shell reaches past it;
:meth:`MainWindow.current_view` is the one place that does the unwrapping.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget


class ScrollHost(QScrollArea):
    """One screen, scrollable when it does not fit."""

    def __init__(self, view: QWidget) -> None:
        super().__init__()
        self.setObjectName("screenScroll")
        self.view = view
        self.setWidgetResizable(True)       # the screen still fills a tall window
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setWidget(view)


def screen_of(widget: QWidget | None) -> QWidget | None:
    """The screen itself, whether or not it is hanging in a scroll host."""
    return getattr(widget, "view", widget)
