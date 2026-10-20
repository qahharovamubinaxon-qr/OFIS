"""ПАТЕНТ screen — the БЕЙДЖИК screen, on the patent blanks.

Everything the operator does here they already do for a badge, so this *is*
the badge's screen: the same regions, the same fields, the same ПР, the same
firm list. What is added on top is the paper itself.

Намуна бланкалар **чексиз**: ҳар юкланган намуна ўз номи билан сақланади
(``templates/patent/blanks/<ном>/front.pdf`` ва ``back.pdf``) ва рўйхатда
алоҳида туради. Шунинг учун иккинчи намуна биринчисининг ўрнига тушмайди —
олдин шундай бўлаётган эди.

Картага босиладиган сон эса тепадаги «Серия» катагида: макет «77» бўлса ҳам,
оператор 416 ёки 33 ни ёзса, картада ўша чиқади.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
)

from src.controllers.patent_controller import PatentController
from src.ui.views.beydjik_view import BeydjikView

#: Рўйхатнинг биринчи қатори — ҳеч нарса юкланмаганда ишлайдигани.
REGION_BLANK = "— регион бланкаси (дастурники ёки ўзингизники) —"


class PatentView(BeydjikView):
    def __init__(self, controller: PatentController) -> None:
        super().__init__(controller)

        title = self.findChild(QLabel, "viewTitle")
        if title is not None:
            title.setText("ПАТЕНТ — ишчининг патент картаси (олд + орқа)")

        row = QHBoxLayout()
        row.addWidget(QLabel("Бланка:"))
        self._blank = QComboBox()
        self._blank.setMinimumWidth(260)
        self._blank.currentIndexChanged.connect(self._show_blank_state)
        row.addWidget(self._blank)
        front = QPushButton("⬆ ОЛД юклаш")
        front.clicked.connect(lambda: self._upload("front"))
        row.addWidget(front)
        back = QPushButton("⬆ ОРҚА юклаш")
        back.clicked.connect(lambda: self._upload("back"))
        row.addWidget(back)
        self.layout().insertLayout(1, row)

        note_row = QHBoxLayout()
        self._blank_note = QLabel()
        self._blank_note.setWordWrap(True)
        self._blank_note.setStyleSheet("color:#8a94a3;")
        note_row.addWidget(self._blank_note, stretch=1)
        self.layout().insertLayout(2, note_row)

        self._region.currentIndexChanged.connect(self._show_blank_state)
        self._reload_blanks()

    # ------------------------------------------------------------------
    def _extra_args(self) -> dict:
        """Танланган намуна — хизматга шу ном билан боради."""
        return {"blank": str(self._blank.currentData() or "")}

    def _reload_blanks(self, keep: str = "") -> None:
        """Рўйхатни қайтадан йиғиш — янги намуна қўшилгач."""
        keep = keep or str(self._blank.currentData() or "")
        self._blank.blockSignals(True)
        self._blank.clear()
        self._blank.addItem(REGION_BLANK, "")
        for found in self._c.blank_sets():
            self._blank.addItem(f"{found.name}  ({found.state()})", found.name)
        index = self._blank.findData(keep)
        self._blank.setCurrentIndex(index if index >= 0 else 0)
        self._blank.blockSignals(False)
        self._show_blank_state()

    def _show_blank_state(self) -> None:
        chosen = str(self._blank.currentData() or "")
        if chosen:
            found = self._c.blank_set(chosen)
            state = (f"«{chosen}» — {found.state()}" if found
                     else f"«{chosen}» топилмади")
            if found is not None and not found.complete:
                state += " ⚠ иккала томонни ҳам юкланг"
        else:
            region = self._region.currentData()
            state = self._c.blank_state(region) if region else "—"
        self._blank_note.setText(
            f"Бланка: {state}.  PDF (олд 1-бет, орқа 2-бет) Рабочий столга "
            "ишчининг фамилияси билан сақланади.")

    # ------------------------------------------------------------------
    def _upload(self, side: str) -> None:
        """Намунани ЎЗ номи билан қўшиш — борини ўчирмайди."""
        which = "ОЛД" if side == "front" else "ОРҚА"
        path, _ = QFileDialog.getOpenFileName(
            self, f"{which} бланка (бўш PDF)", "", "PDF (*.pdf)")
        if not path:
            return
        suggested = str(self._blank.currentData() or "") or Path(path).stem
        name, agreed = QInputDialog.getText(
            self, "Бланка номи",
            "Бу намуна қайси ном билан сақлансин?\n"
            "(шу ном билан рўйхатда алоҳида туради)", text=suggested)
        if not agreed or not name.strip():
            return
        try:
            self._c.import_blank_set(name.strip(), side, Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload_blanks(keep=self._c.safe_name(name.strip()))
        self._status.setText(f"✅ «{name.strip()}» намунасига {which} бланка "
                             "юкланди.")
