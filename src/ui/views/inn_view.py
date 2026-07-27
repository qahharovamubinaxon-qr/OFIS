"""ИНН screen — the office's own record sheet of a worker's tax number.

Drop the worker's passport (or patent), pick the date, type the twelve digits
of the ИНН → RUN. The sheet is saved as a PDF for the worker's folder.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.threading import run_async
from src.controllers.inn_controller import InnController
from src.services.inn_service import INN_DIGITS, InnResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class InnView(QWidget):
    def __init__(self, controller: InnController) -> None:
        super().__init__()
        self._c = controller
        self._result: InnResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ИНН — ишчининг ИНН рақами варағи")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        row.addWidget(QLabel("Кун:"))
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(self._date)
        row.addSpacing(20)
        row.addWidget(QLabel("ИНН рақами:"))
        self._inn = QLineEdit()
        self._inn.setPlaceholderText(f"{INN_DIGITS} та рақам")
        self._inn.setMaxLength(20)
        self._inn.setFixedWidth(200)
        self._inn.textChanged.connect(self._show_count)
        row.addWidget(self._inn)
        self._count = QLabel()
        self._count.setStyleSheet("color:#8a94a3;")
        row.addWidget(self._count)
        row.addStretch(1)
        root.addLayout(row)

        self._dz = DropZone("🛂", "Ишчининг паспорти ёки патенти")
        root.addWidget(self._dz, stretch=1)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (ИНН)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._run_ai)
        actions.addWidget(self._run)
        self._open = QPushButton("📂 Папкани очиш")
        self._open.setEnabled(False)
        self._open.clicked.connect(self._open_folder)
        actions.addWidget(self._open)
        actions.addStretch(1)
        root.addLayout(actions)

        self._progress = RunProgress()
        root.addWidget(self._progress)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel(
            "Паспорт ёки патент расмини юкланг, кунни танланг ва ИНН рақамини "
            "ёзинг. Ф.И.О., жинси, туғилган санаси ва фуқаролиги ҳужжатдан "
            "олинади.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

        self._show_count()

    # ------------------------------------------------------------------
    def _show_count(self) -> None:
        digits = "".join(c for c in self._inn.text() if c.isdigit())
        if not digits:
            self._count.setText("")
        elif len(digits) == INN_DIGITS:
            self._count.setText("✅")
        else:
            self._count.setText(f"{len(digits)}/{INN_DIGITS}")

    def _form_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    def _run_ai(self) -> None:
        if self._dz.path is None:
            self._warn("Ишчининг паспорти ёки патенти расмини юкланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalarга Gemini калитини киритинг.")
            return
        digits = "".join(c for c in self._inn.text() if c.isdigit())
        if len(digits) != INN_DIGITS:
            self._warn(f"ИНН {INN_DIGITS} та рақамдан иборат бўлиши керак "
                       f"(ҳозир {len(digits)} та).")
            return

        data = Path(self._dz.path).read_bytes()
        self._run.setEnabled(False)
        self._status.setText("⏳ Ҳужжат ўқилаяпти ва варақ тайёрланяпти…")
        self._progress.start("ИНН варағи тайёрланяпти…")
        run_async(self._c.generate_from_image, data,
                  inn=digits, form_date=self._form_date(),
                  on_success=self._done, on_error=self._failed)

    def _done(self, result: InnResult) -> None:
        self._run.setEnabled(True)
        self._open.setEnabled(True)
        self._progress.finish()
        self._result = result
        self._dz.clear()
        self._inn.clear()
        self._status.setText(
            f"✅ {result.surname} — ИНН {result.inn}\n{result.pdf_path}")

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + message)
        QMessageBox.warning(self, "Xato", message)

    def _open_folder(self) -> None:
        if self._result is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._result.pdf_path.parent)))

    def _warn(self, message: str) -> None:
        self._status.setText("⚠️ " + message)
        QMessageBox.information(self, "Diqqat", message)

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        self._dz.clear()
        self._inn.clear()
        self._result = None
        self._open.setEnabled(False)
        self._show_count()
