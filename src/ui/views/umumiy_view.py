"""УМУМИЙ screen — reuse any office document for a new worker.

Drop the existing document (text PDF), the new worker's passport (+ patent /
migration card), pick the document date → RUN. The program finds the previous
worker's details inside the document and replaces them with the new worker's.
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
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.threading import run_async
from src.ocr.service import OcrService
from src.services.umumiy_service import UmumiyResult, UmumiyService
from src.ui.widgets.multi_drop import PDF_EXTS, MultiDropZone
from src.ui.widgets.run_progress import RunProgress


class UmumiyView(QWidget):
    def __init__(self, ocr: OcrService, service: UmumiyService) -> None:
        super().__init__()
        self._ocr = ocr
        self._svc = service

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("УМУМИЙ — ҳужжатни янги ишчига мослаш")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- date --------------------------------------------------------
        row = QHBoxLayout()
        row.addWidget(QLabel("Ҳужжат санаси:"))
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(self._date)
        row.addStretch(1)
        root.addLayout(row)

        # -- two drop areas side by side ---------------------------------
        up = QHBoxLayout()
        up.setSpacing(14)
        self._dz_doc = MultiDropZone(
            "Ҳужжат (PDF) — қайта ишланадиган", limit=1,
            exts=PDF_EXTS, icon="📄", min_height=170)
        self._dz_worker = MultiDropZone(
            "Ишчи ҳужжатлари — паспорт · патент · миграционка (хоҳлаганча)",
            limit=10, icon="🛂", min_height=170)
        up.addWidget(self._dz_doc, stretch=1)
        up.addWidget(self._dz_worker, stretch=1)
        root.addLayout(up, stretch=1)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (Умумий)")
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
            "Ҳужжат матнли PDF бўлиши керак (скан эмас). Фирма реквизитлари "
            "(ИНН, ОГРН, директор) ўзгартирилмайди — фақат ишчи маълумотлари."
        )
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

    # ------------------------------------------------------------------
    def _form_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    def _run_ai(self) -> None:
        if not self._dz_doc.files:
            self._warn("Аввал қайта ишланадиган ҳужжатни (PDF) юкланг.")
            return
        if not self._ocr.available():
            self._warn("AI калити йўқ — Sozlamalarга Gemini калитини киритинг.")
            return
        if not self._dz_worker.files:
            self._warn("Ишчининг камида битта ҳужжат расмини юкланг "
                       "(паспорт, патент ёки миграционка).")
            return

        source = self._dz_doc.files[0]
        images = [f.read_bytes() for f in self._dz_worker.files]
        form_date = self._form_date()

        def work():
            # Any mix of worker documents is accepted: the first image is read
            # as the identity document, the rest add patent/migration details.
            passport, patent = self._ocr.read_documents(
                images[0],
                images[1] if len(images) > 1 else None,
                images[2] if len(images) > 2 else None,
            )
            return self._svc.generate(source, passport, patent, form_date=form_date)

        self._run.setEnabled(False)
        self._status.setText("⏳ AI ҳужжатни ўқияпти ва янги ишчига мослаяпти…")
        self._progress.start("Ҳужжат тайёрланяпти…")
        run_async(work, on_success=self._done, on_error=self._failed)

    # ------------------------------------------------------------------
    def _done(self, result: UmumiyResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        self._dz_worker.clear_files()
        from src.ui.widgets.save_to import ask_save_dir

        saved = ask_save_dir(self, [result.pdf_path])
        extra = f" → {saved}" if saved else ""
        self._status.setText(
            f"✅ Тайёр: {result.pdf_path.name}  ·  {result.replacements} та "
            f"маълумот алмаштирилди{extra}")
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"Ҳужжат тайёр:\n{result.pdf_path}\n\n"
                    f"Алмаштирилган маълумотлар: {result.replacements} та\n"
                    "Илтимос, чоп этишдан олдин текшириб чиқинг.")
        open_btn = box.addButton("Papkani ochish", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            _open_folder(result.pdf_path.parent)

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        msg = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + msg)
        self._warn(msg)

    def _warn(self, msg: str) -> None:
        QMessageBox.warning(self, "Diqqat", msg)


def _open_folder(folder: Path) -> None:
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(folder)])  # noqa: S603,S607
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603,S607
    except OSError:
        pass
