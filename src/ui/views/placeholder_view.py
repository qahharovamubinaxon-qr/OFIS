"""A neutral placeholder page used by the shell until each real screen lands in
its own phase (Dashboard → Phase 4, Process → Phase 6, etc.). It is a real,
themed widget — not a hack — so the navigation and layout are testable now.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderView(QWidget):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        heading = QLabel(title)
        heading.setObjectName("viewTitle")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("viewSubtitle")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(sub)
