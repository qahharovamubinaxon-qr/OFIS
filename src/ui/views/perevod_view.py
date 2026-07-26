"""ПЕРЕВОД screen — notarial translation of personal documents into Russian.

Drop the document photos (front/back — passport, driving licence, birth or
marriage certificate, diploma, аттестат …), leave the type on «Авто» and RUN.
The program recognises the document, translates every field and saves the
standard notarial-translation PDF + Word for the notary to certify.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
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
from src.services.perevod_service import DOC_TYPES, PerevodResult, PerevodService
from src.ui.widgets.multi_drop import MultiDropZone
from src.ui.widgets.run_progress import RunProgress


class PerevodView(QWidget):
    def __init__(self, service: PerevodService) -> None:
        super().__init__()
        self._svc = service

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ПЕРЕВОД — нотариал таржима (рус тилига)")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        self._type = QComboBox()
        for _key, label in DOC_TYPES:
            self._type.addItem(label)
        row.addWidget(QLabel("Ҳужжат тури:"))
        row.addWidget(self._type, stretch=2)
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(QLabel("Сана:"))
        row.addWidget(self._date)
        root.addLayout(row)

        self._dz = MultiDropZone(
            "Ҳужжат расмлари — олд/орқа томон (10 тагача)")
        root.addWidget(self._dz, stretch=1)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (Перевод)")
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
            "Таржима PDF + Word бўлиб сақланади — нотариус текшириб тасдиқлайди. "
            "Паспорт · ҳайдовчилик гувоҳномаси · туғилганлик/никоҳ гувоҳномаси · "
            "диплом · аттестат қўллаб-қувватланади."
        )
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

    # ------------------------------------------------------------------
    def _run_ai(self) -> None:
        if not self._dz.files:
            QMessageBox.warning(self, "Diqqat", "Камида битта ҳужжат расмини танланг.")
            return
        images = [f.read_bytes() for f in self._dz.files]
        doc_type = DOC_TYPES[self._type.currentIndex()][0]
        q = self._date.date()
        form_date = date(q.year(), q.month(), q.day())

        def work():
            return self._svc.translate(images, doc_type=doc_type, form_date=form_date)

        self._run.setEnabled(False)
        self._status.setText("⏳ AI ҳужжатни ўқияпти ва таржима қиляпти…")
        self._progress.start("Таржима тайёрланяпти…")
        run_async(work, on_success=self._done, on_error=self._failed)

    def _done(self, result: PerevodResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        self._dz.clear_files()
        from src.ui.widgets.save_to import ask_save_dir

        saved = ask_save_dir(self, [result.pdf_path, result.docx_path])
        extra = f" → {saved}" if saved else ""
        self._status.setText(
            f"✅ Тайёр: {result.title} ({result.doc_type}) — "
            f"{result.pdf_path.name} + Word{extra}")
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"Таржима тайёр:\n{result.pdf_path}\n{result.docx_path}\n\n"
                    "Илтимос, нотариусга беришдан олдин текшириб чиқинг.")
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
        QMessageBox.warning(self, "Xato", msg)


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
