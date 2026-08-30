"""The pieces that give every screen the same modern header and fields.

Two small builders, used across the views so the whole program reads as one
designed thing rather than a set of forms:

* :func:`header` — the screen's title, an optional one-line description under
  it, and an optional status chip pushed to the right. The coloured hairline
  under it is the section's own paper colour (styled by ``#viewTitle``).
* :func:`field` — a control with a small upper-case label ABOVE it, the way a
  modern form labels its inputs, rather than a word crammed in beside them.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


def header(title: str, subtitle: str = "", badge: str = "") -> QWidget:
    """The title block: big title, a description under it, a chip on the right."""
    wrap = QWidget()
    outer = QVBoxLayout(wrap)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    top = QHBoxLayout()
    top.setContentsMargins(0, 0, 0, 0)
    top.setSpacing(12)

    left = QVBoxLayout()
    left.setContentsMargins(0, 0, 0, 0)
    left.setSpacing(6)
    label = QLabel(title)
    label.setObjectName("viewTitle")
    left.addWidget(label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("viewSubtitle")
        sub.setWordWrap(True)
        left.addWidget(sub)
    top.addLayout(left, stretch=1)

    if badge:
        chip = QLabel(badge)
        chip.setObjectName("viewBadge")
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(chip, alignment=Qt.AlignmentFlag.AlignTop)

    outer.addLayout(top)
    return wrap


def field(label: str, control: QWidget, *, stretch: int = 0) -> QVBoxLayout:
    """A control with a small upper-case label sitting above it."""
    box = QVBoxLayout()
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(5)
    cap = QLabel(label.upper())
    cap.setObjectName("fieldLabel")
    box.addWidget(cap)
    box.addWidget(control, stretch=stretch)
    return box
