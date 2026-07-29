"""The ППУ section — two screens behind one switch.

The office prints two different packages from the same corner of its filing:
the ordinary **ППУ** pair off a регистрация, and **ТРУД ППУ**, three sheets off
the worker's трудовой договор, уведомление and patent. They share the front
sheet and nothing else, so they are two screens with a switch above them rather
than one screen with half its fields greyed out.

The switch is the same one РАСМ-ФОТО uses for «Nima kerak»: a combo box that
changes which screen is shown and nothing else. Neither screen knows about the
other, and the ППУ screen is untouched by this being here.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.controllers.ppu_controller import PpuController
from src.controllers.trud_ppu_controller import TrudPpuController
from src.ui.views.ppu_view import PpuView
from src.ui.views.trud_ppu_view import TrudPpuView


class PpuSectionView(QWidget):
    def __init__(self, controller: PpuController,
                 trud_controller: TrudPpuController) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QHBoxLayout()
        bar.setContentsMargins(28, 16, 28, 0)
        bar.addWidget(QLabel("Nima kerak:"))
        self._mode = QComboBox()
        self._mode.addItem("🧾 ППУ — регистрациядан", "ppu")
        self._mode.addItem("🧷 ТРУД ППУ — патент ва трудовойдан", "trud")
        self._mode.setFixedWidth(300)
        self._mode.setToolTip(
            "ППУ — регистрациядан олд + орқа.\n"
            "ТРУД ППУ — трудовой, уведомление ва патентдан уч саҳифа.")
        self._mode.currentIndexChanged.connect(self._on_mode)
        bar.addWidget(self._mode)
        bar.addStretch(1)
        root.addLayout(bar)

        self._stack = QStackedWidget()
        self._ppu = PpuView(controller)
        self._trud = TrudPpuView(trud_controller, controller.templates)
        self._stack.addWidget(self._ppu)
        self._stack.addWidget(self._trud)
        root.addWidget(self._stack, stretch=1)

    def _on_mode(self) -> None:
        self._stack.setCurrentIndex(self._mode.currentIndex())
        # a blank uploaded on one screen must show up in the other's list
        self._trud.reload_templates()

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        """Clear whichever screen the operator is on; the other keeps its work."""
        current = self._stack.currentWidget()
        if hasattr(current, "reset"):
            current.reset()
