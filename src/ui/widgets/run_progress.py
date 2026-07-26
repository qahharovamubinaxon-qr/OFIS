"""A modern percent progress bar for PDF generation.

Generation is one opaque async call, so the bar animates smoothly toward 90%
while work is running (fast at first, slowing near the end — feels live), then
snaps to 100% on success. ``fail()`` turns it red. Hidden when idle.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

_BAR_QSS = """
QProgressBar {
    border: none; border-radius: 7px; background: rgba(127, 140, 160, 0.22);
    min-height: 14px; max-height: 14px; text-align: center; color: transparent;
}
QProgressBar::chunk {
    border-radius: 7px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #4f8cff, stop:1 #2fbf71);
}
"""
_BAR_QSS_FAIL = _BAR_QSS.replace("#4f8cff", "#ff6b6b").replace("#2fbf71", "#e03131")


class RunProgress(QWidget):
    """start(text) → animates to 90% · finish() → 100% · fail() → red stop."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(10)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setStyleSheet(_BAR_QSS)
        self._pct = QLabel("0%")
        self._pct.setStyleSheet("font-weight: 600; min-width: 42px;")
        self._text = QLabel("")
        self._text.setStyleSheet("color:#8a94a3;")

        row.addWidget(self._bar, stretch=1)
        row.addWidget(self._pct)
        row.addWidget(self._text, stretch=1)

        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self._value = 0.0
        self.hide()

    # ------------------------------------------------------------------
    def start(self, text: str = "") -> None:
        self._value = 0.0
        self._bar.setStyleSheet(_BAR_QSS)
        self._text.setText(text)
        self._apply()
        self.show()
        self._timer.start()

    def finish(self) -> None:
        self._timer.stop()
        self._value = 100.0
        self._apply()
        QTimer.singleShot(1200, self.hide)

    def fail(self) -> None:
        self._timer.stop()
        self._bar.setStyleSheet(_BAR_QSS_FAIL)
        QTimer.singleShot(1500, self.hide)

    # ------------------------------------------------------------------
    def _tick(self) -> None:
        # Ease toward 90: big steps early, tiny near the cap — never reaches it.
        self._value += max(0.15, (90.0 - self._value) * 0.045)
        self._value = min(self._value, 90.0)
        self._apply()

    def _apply(self) -> None:
        v = int(round(self._value))
        self._bar.setValue(v)
        self._pct.setText(f"{v}%")
