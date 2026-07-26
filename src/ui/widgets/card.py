"""A titled settings card — the building block of the Settings screen.

Groups related controls under a heading and an optional one-line description,
inside a rounded panel styled by the active theme (``#card`` in the QSS).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget


class Card(QWidget):
    def __init__(self, icon: str, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("card")
        # a plain QWidget ignores QSS background/border without this
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 18)
        outer.setSpacing(4)

        head = QLabel(f"{icon}  {title}" if icon else title)
        head.setObjectName("cardTitle")
        outer.addWidget(head)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("cardSubtitle")
            sub.setWordWrap(True)
            outer.addWidget(sub)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 10, 0, 0)
        self._body.setSpacing(10)
        outer.addLayout(self._body)

    # ------------------------------------------------------------------
    def add(self, widget_or_layout) -> None:
        if isinstance(widget_or_layout, QWidget):
            self._body.addWidget(widget_or_layout)
        else:
            self._body.addLayout(widget_or_layout)

    def form(self) -> QFormLayout:
        """A form laid out inside the card (labels left, controls right)."""
        f = QFormLayout()
        f.setVerticalSpacing(10)
        f.setHorizontalSpacing(14)
        f.setContentsMargins(0, 0, 0, 0)
        self._body.addLayout(f)
        return f

    def note(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cardNote")
        label.setWordWrap(True)
        self._body.addWidget(label)
        return label
