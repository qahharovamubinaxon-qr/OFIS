"""ДМС screen — the office's РЕСО «ДМС-Трудовой» policy for one worker.

Drop the worker's passport, pick the start date, type the phone and the
registration address → RUN. Everything else comes off the passport, the end
date is a year less a day, and the policy number is taken from the block РЕСО
allocated to the agency (Sozlamalar → ДМС).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
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
from src.controllers.dms_controller import DmsController
from src.services.dms_service import DmsResult, policy_end_date
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class DmsView(QWidget):
    def __init__(self, controller: DmsController) -> None:
        super().__init__()
        self._c = controller
        self._result: DmsResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ДМС — полис «ДМС-Трудовой»")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        self._counter = QLabel()
        self._counter.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._counter)

        # -- dates -------------------------------------------------------
        row = QHBoxLayout()
        row.addWidget(QLabel("Бошланиш санаси:"))
        self._start = QDateEdit()
        self._start.setDisplayFormat("dd.MM.yyyy")
        self._start.setDate(QDate.currentDate())
        self._start.setCalendarPopup(True)
        self._start.dateChanged.connect(self._sync_end)
        row.addWidget(self._start)
        self._end = QLabel()
        self._end.setStyleSheet("font-weight:600;")
        row.addWidget(self._end)
        row.addStretch(1)
        root.addLayout(row)

        # -- typed fields ------------------------------------------------
        fields = QHBoxLayout()
        self._phone = QLineEdit()
        self._phone.setPlaceholderText("+7 968 394-10-08")
        self._address = QLineEdit()
        self._address.setPlaceholderText("Москва, Вяземская улица, 1к1, кв. 62")
        self._region = QLineEdit()
        self._region.setPlaceholderText("Москва")
        self._region.setFixedWidth(140)
        for label, widget, stretch in (("Телефон:", self._phone, 1),
                                       ("Рўйхат манзили:", self._address, 3),
                                       ("Патент ҳудуди:", self._region, 0)):
            fields.addWidget(QLabel(label))
            fields.addWidget(widget, stretch=stretch)
        root.addLayout(fields)

        # -- passport ----------------------------------------------------
        self._dz = DropZone("🛂", "Ишчининг паспортини юкланг")
        root.addWidget(self._dz, stretch=1)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (ДМС)")
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

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

        self._sync_end()
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        nxt, left = self._c.next_number(), self._c.remaining()
        if nxt:
            self._counter.setText(f"Кейинги полис рақами: {nxt}   ·   қолди: {left} та")
            self._status.setText(
                "Паспортни юкланг, санани танланг, телефон ва манзилни ёзинг.")
        else:
            self._counter.setText("⚠️  Полис рақамлари киритилмаган")
            self._status.setText(
                "Sozlamalar → ДМС бўлимига РЕСО берган рақамлар оралиғини "
                "киритинг — программа фақат ўша оралиқдаги рақамларни ишлатади.")

    def _sync_end(self) -> None:
        q = self._start.date()
        end = policy_end_date(date(q.year(), q.month(), q.day()))
        self._end.setText(f"→  тугаши: {end.strftime('%d.%m.%Y')}")

    def _start_date(self) -> date:
        q = self._start.date()
        return date(q.year(), q.month(), q.day())

    # ------------------------------------------------------------------
    def _run_ai(self) -> None:
        if self._dz.path is None:
            self._warn("Ишчининг паспорт расмини юкланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalarга Gemini калитини киритинг.")
            return
        if not self._address.text().strip():
            self._warn("Рўйхатдан ўтиш манзилини ёзинг.")
            return
        if not self._c.next_number():
            self._warn("Полис рақами йўқ — Sozlamalar → ДМС бўлимига РЕСО "
                       "берган рақамлар оралиғини киритинг.")
            return

        data = Path(self._dz.path).read_bytes()
        self._run.setEnabled(False)
        self._status.setText("⏳ Паспорт ўқилаяпти ва полис тайёрланяпти…")
        self._progress.start("Полис тайёрланяпти…")
        run_async(
            self._c.generate_from_images, data,
            start_date=self._start_date(),
            phone=self._phone.text().strip(),
            address=self._address.text().strip(),
            region=self._region.text().strip() or None,
            on_success=self._done, on_error=self._failed,
        )

    def _done(self, result: DmsResult) -> None:
        self._run.setEnabled(True)
        self._open.setEnabled(True)
        self._progress.finish()
        self._result = result
        self._dz.clear()
        self.refresh()
        self._status.setText(
            f"✅ Полис № {result.policy_number} тайёр  ·  "
            f"{result.start_date.strftime('%d.%m.%Y')} — "
            f"{result.end_date.strftime('%d.%m.%Y')}\n{result.pdf_path}")

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + message)
        QMessageBox.warning(self, "Xato", message)

    def _open_folder(self) -> None:
        if self._result is None:
            return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._result.pdf_path.parent)))

    def _warn(self, message: str) -> None:
        self._status.setText("⚠️ " + message)
        QMessageBox.information(self, "Diqqat", message)

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        self._dz.clear()
        self._phone.clear()
        self._address.clear()
        self._result = None
        self._open.setEnabled(False)
        self.refresh()
