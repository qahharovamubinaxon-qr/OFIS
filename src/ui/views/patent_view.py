"""ПАТЕНТ screen — the БЕЙДЖИК screen, on the patent blanks.

Everything the operator does here they already do for a badge, so this *is*
the badge's screen: the same regions, the same fields, the same ПР, the same
firm list. Two things are added on top — a row for uploading the office's own
front and back, and a note saying which blank is being printed on.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from src.controllers.patent_controller import PatentController
from src.ui.views.beydjik_view import BeydjikView


class PatentView(BeydjikView):
    def __init__(self, controller: PatentController) -> None:
        super().__init__(controller)

        title = self.findChild(QLabel, "viewTitle")
        if title is not None:
            title.setText("ПАТЕНТ — ишчининг патент картаси (олд + орқа)")

        row = QHBoxLayout()
        self._blank_note = QLabel()
        self._blank_note.setStyleSheet("color:#8a94a3;")
        row.addWidget(self._blank_note, stretch=1)
        front = QPushButton("⬆ ОЛД бланкани юклаш")
        front.clicked.connect(lambda: self._upload("front"))
        row.addWidget(front)
        back = QPushButton("⬆ ОРҚА бланкани юклаш")
        back.clicked.connect(lambda: self._upload("back"))
        row.addWidget(back)
        self.layout().insertLayout(1, row)

        self._region.currentIndexChanged.connect(self._show_blank_state)
        self._show_blank_state()

    # ------------------------------------------------------------------
    def _show_blank_state(self) -> None:
        region = self._region.currentData()
        if not region:
            return
        state = self._c.blank_state(region)
        self._blank_note.setText(
            f"Бланка: {state}.  PDF (олд 1-бет, орқа 2-бет) Рабочий столга "
            "ишчининг фамилияси билан сақланади.")

    def _upload(self, side: str) -> None:
        region = self._region.currentData()
        if not region:
            return
        which = "ОЛД" if side == "front" else "ОРҚА"
        path, _ = QFileDialog.getOpenFileName(
            self, f"{which} бланка (бўш PDF)", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            self._c.import_blank(region, side, Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._show_blank_state()
        self._status.setText(f"✅ {which} бланка юкланди ({region}).")
