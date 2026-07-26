"""ДОВЕРЕННОСТЬ screen — notarial drafts for the office's notary.

Drop the доверитель's passport (+ optionally the representative's), pick the
date and document type (or leave «Авто» and just describe the task), write who
→ whom → for what, RUN → the draft is saved as Word AND PDF for the notary to
certify.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from src.common.errors import OfisError
from src.common.threading import run_async
from src.ocr.service import OcrService
from src.services.dover_service import DOVER_TYPES, DoverResult, DoverService
from src.ui.widgets.multi_drop import MultiDropZone
from src.ui.widgets.run_progress import RunProgress


class DoverView(QWidget):
    def __init__(self, ocr: OcrService, service: DoverService) -> None:
        super().__init__()
        self._ocr = ocr
        self._svc = service

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ДОВЕРЕННОСТЬ — нотариал ҳужжат тайёрлаш")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        self._type = QComboBox()
        self._type.addItems(DOVER_TYPES)
        row.addWidget(QLabel("Тури:"))
        row.addWidget(self._type, stretch=2)
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(QLabel("Сана:"))
        row.addWidget(self._date)
        root.addLayout(row)

        self._dz = MultiDropZone("Hujjat rasmlari — pasport(lar), СТС va h.k. (15 tagacha)")
        root.addWidget(self._dz, stretch=1)

        self._desc = QTextEdit()
        self._desc.setPlaceholderText(
            "Кимдан кимга, нима мақсадда берилади — эркин ёзинг. "
            "Тур танланмаса дастур ўзи аниқлайди."
        )
        self._desc.setMaximumHeight(110)
        root.addWidget(self._desc)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (Доверенность)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._run_ai)
        actions.addWidget(self._run)
        actions.addStretch(1)
        root.addLayout(actions)

        self._progress = RunProgress()
        root.addWidget(self._progress)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel(
            "Нusxa Word + PDF бўлиб сақланади — нотариус кўриб имзолайди."
        )
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

    # ------------------------------------------------------------------
    def _run_ai(self) -> None:
        if not self._dz.files:
            QMessageBox.warning(self, "Diqqat", "Kamida bitta hujjat rasmini tanlang.")
            return
        if not self._ocr.available():
            QMessageBox.warning(self, "Diqqat", "AI kaliti yo'q — Sozlamalarga kiriting.")
            return
        images = [f.read_bytes() for f in self._dz.files]
        q = self._date.date()
        form_date = date(q.year(), q.month(), q.day())
        doc_type = self._type.currentText()
        description = self._desc.toPlainText().strip()

        def work():
            return self._svc.generate_from_images(
                images, doc_type=doc_type, description=description,
                form_date=form_date)

        self._run.setEnabled(False)
        self._status.setText("⏳ AI ҳужжат матнини тузяпти…")
        self._progress.start("Доверенность тайёрланяпти…")
        run_async(work, on_success=self._done, on_error=self._failed)

    def _done(self, result: DoverResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        self._dz.clear_files()
        from src.ui.widgets.save_to import ask_save_dir

        saved = ask_save_dir(self, [result.pdf_path, result.docx_path])
        extra = f" → {saved}" if saved else ""
        nums = (f"  |  Бланк: {result.series} · Реестр № {result.reestr}"
                if result.series else "")
        self._status.setText(
            f"✅ Tayyor: {result.pdf_path.name} + Word нусхаси{nums}{extra}")
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(
            f"Ҳужжат тайёр:\n{result.pdf_path}\n{result.docx_path}\n\n"
            f"Бланк серияси: {result.series}\nРеестр №: {result.reestr}")
        open_btn = box.addButton("Papkani ochish", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            import subprocess
            import sys

            try:
                if sys.platform == "win32":
                    subprocess.Popen(["explorer", str(result.pdf_path.parent)])  # noqa: S603,S607
                else:
                    subprocess.Popen(["xdg-open", str(result.pdf_path.parent)])  # noqa: S603,S607
            except OSError:
                pass

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        msg = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + msg)
        QMessageBox.warning(self, "Xato", msg)
