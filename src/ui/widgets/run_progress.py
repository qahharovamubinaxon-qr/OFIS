"""What the program is doing right now, as a ring with the figure inside it.

The bar this replaces counted nothing. Generation was one opaque call, so the
bar crawled toward 90 % on a timer and snapped to 100 % when the call came
back — a number that looked like progress and measured nothing. The office
learned to ignore it, which is the worst thing an indicator can teach.

So there are two modes, and the difference between them is the whole point:

* :meth:`start` — nobody can say how far along this is. The ring SWEEPS and
  the middle stays empty. It says «working», which is true, and nothing more.
* :meth:`start_steps` — the work is a known list of steps and each one
  reports when it is done. The ring fills by steps completed and the middle
  shows the percent, because now the percent is real.

A caller that cannot name its steps gets the sweep. No number is better than
an invented one.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.ui.widgets.ring_gauge import RingGauge

#: How far the sweeping arc reaches round the dial while work is running.
_SWEEP_SHARE = 0.26
#: Degrees the sweep travels per tick, and how often a tick comes.
_SWEEP_STEP = 9.0
_SWEEP_MS = 40
#: How long the finished ring stays on screen before it gets out of the way.
_LINGER_MS = 1200
_LINGER_FAIL_MS = 2200


class RunProgress(QWidget):
    """start(text) → sweep · start_steps([…]) + step_done() → real percent."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(14)

        self._ring = RingGauge(diameter=56, thickness=6)
        row.addWidget(self._ring)

        column = QVBoxLayout()
        column.setSpacing(3)
        self._text = QLabel("")
        self._text.setObjectName("runProgressText")
        self._step = QLabel("")
        self._step.setObjectName("runProgressStep")
        column.addWidget(self._text)
        column.addWidget(self._step)
        row.addLayout(column)
        row.addStretch(1)

        self._steps: list[str] = []
        self._done = 0
        self._angle = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(_SWEEP_MS)
        self._timer.timeout.connect(self._sweep)
        self.hide()

    # ----------------------------------------------------------- starting
    def start(self, text: str = "") -> None:
        """Work with no countable steps: sweep, and say nothing about how far."""
        self._steps, self._done = [], 0
        self._text.setText(text)
        self._step.setText("")
        self._ring.set_centre("")
        self._ring.set_progress(_SWEEP_SHARE)
        self._angle = 0.0
        self._ring.set_start_angle(0.0)
        self.show()
        self._timer.start()

    def start_steps(self, steps: list[str], text: str = "") -> None:
        """Work whose steps are known. The ring now counts something real.

        An empty list is not a zero-step job — it is a caller that does not
        know its steps, so it falls back to the sweep rather than dividing
        by nothing.
        """
        names = [str(s) for s in steps if str(s).strip()]
        if not names:
            self.start(text)
            return
        self._timer.stop()
        self._steps, self._done = names, 0
        self._text.setText(text)
        self._step.setText(names[0])
        self._ring.set_start_angle(0.0)
        self._apply()
        self.show()

    # ----------------------------------------------------------- advancing
    def step_done(self, label: str | None = None) -> None:
        """One named step finished. Ignored when the ring is only sweeping —
        a caller that mixes the two modes must not be able to invent a figure.
        """
        if not self._steps:
            return
        self._done = min(len(self._steps), self._done + 1)
        if label is not None:
            self._step.setText(str(label))
        elif self._done < len(self._steps):
            self._step.setText(self._steps[self._done])
        self._apply()

    def steps_done(self) -> int:
        return self._done

    def percent(self) -> int:
        """What the middle says — 0 when there is nothing honest to say."""
        if not self._steps:
            return 0
        return int(round(100.0 * self._done / len(self._steps)))

    # ------------------------------------------------------------- ending
    def finish(self) -> None:
        self._timer.stop()
        if self._steps:
            self._done = len(self._steps)
            self._apply()
        else:
            self._ring.set_progress(1.0)
            self._ring.set_centre("100", "%")
        self._step.setText("")
        QTimer.singleShot(_LINGER_MS, self.hide)

    def fail(self, reason: str = "") -> None:
        """Stop where it stopped. The ring keeps the figure it had reached —
        how far it got before the failure is the useful part."""
        self._timer.stop()
        self._ring.set_colours("#E2685F", "#1C2733", "#E8EEF2", "#60707E")
        if reason:
            self._step.setText(reason)
        QTimer.singleShot(_LINGER_FAIL_MS, self._reset_and_hide)

    def _reset_and_hide(self) -> None:
        self._ring.set_colours("#FF7A18", "#1C2733", "#E8EEF2", "#60707E")
        self.hide()

    # ------------------------------------------------------------ painting
    def _apply(self) -> None:
        total = len(self._steps)
        self._ring.set_progress(self._done / total if total else 0.0)
        self._ring.set_centre(str(self.percent()), "%")

    def _sweep(self) -> None:
        self._angle = (self._angle + _SWEEP_STEP) % 360.0
        self._ring.set_start_angle(self._angle)
