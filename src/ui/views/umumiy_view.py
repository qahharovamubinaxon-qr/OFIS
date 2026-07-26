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
    QFileDialog,
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
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class UmumiyView(QWidget):
    def __init__(self, ocr: OcrService, service: UmumiyService) -> None:
        super().__init__()
        self._ocr = ocr
        self._svc = service
        self._doc: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("УМУМИЙ — ҳужжатни янги ишчига мослаш")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- source document + date -------------------------------------
        row = QHBoxLayout()
        self._doc_label = QLabel("Ҳужжат танланмаган (PDF)")
        pick = QPushButton("📄  Ҳужжат танлаш (PDF)")
        pick.clicked.connect(self._pick_doc)
        row.addWidget(pick)
        row.addWidget(self._doc_label, stretch=1)
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(QLabel("Сана:"))
        row.addWidget(self._date)
        root.addLayout(row)

        # -- worker documents -------------------------------------------
        up = QHBoxLayout()
        up.setSpacing(12)
        self._dz_passport = DropZone("🛂", "Паспорт")
        self._dz_patent = DropZone("📄", "Патент / Миграционка (олд)")
        self._dz_patent_back = DropZone("🔄", "Патент (орқа)")
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            up.addWidget(dz, stretch=1)
        root.addLayout(up)

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
    def _pick_doc(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ҳужжат (PDF)", "", "PDF (*.pdf)")
        if path:
            self._doc = Path(path)
            self._doc_label.setText(f"✓ {self._doc.name}")

    def _form_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    def _run_ai(self) -> None:
        if self._doc is None:
            self._warn("Аввал ҳужжат (PDF) танланг.")
            return
        if not self._ocr.available():
            self._warn("AI калити йўқ — Sozlamalarга Gemini калитини киритинг.")
            return
        if self._dz_passport.path is None:
            self._warn("Янги ишчининг паспорт расмини юкланг.")
            return

        passport_img = self._dz_passport.path.read_bytes()
        patent_img = (self._dz_patent.path.read_bytes()
                      if self._dz_patent.path else None)
        back_img = (self._dz_patent_back.path.read_bytes()
                    if self._dz_patent_back.path else None)
        source = self._doc
        form_date = self._form_date()

        def work():
            passport, patent = self._ocr.read_documents(
                passport_img, patent_img, back_img)
            return self._svc.generate(source, passport, patent, form_date=form_date)

        self._run.setEnabled(False)
        self._status.setText("⏳ AI ҳужжатни ўқияпти ва янги ишчига мослаяпти…")
        self._progress.start("Ҳужжат тайёрланяпти…")
        run_async(work, on_success=self._done, on_error=self._failed)

    # ------------------------------------------------------------------
    def _done(self, result: UmumiyResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            dz.clear()
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
