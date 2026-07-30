"""ПЕРЕВОД screen — notarial translation of personal documents into Russian.

The office prints its translations on its own three pre-printed sheets, so they
are uploaded here once and kept: sheet 1 the copy of the original is centred on,
sheet 2 the translation is set on, sheet 3 the notary completes by hand. All
three come out as one three-page PDF.

Drop the document photos (front/back — passport, driving licence, birth or
marriage certificate, diploma, аттестат …), leave the type on «Авто» and RUN.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
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
from src.services.perevod_service import DOC_TYPES, PerevodResult, PerevodService
from src.ui.widgets.multi_drop import MultiDropZone
from src.ui.widgets.run_progress import RunProgress

#: What the office may hand over as a blank, as a file dialog filter.
_BLANK_FILTER = "Бланка (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"

#: What each sheet is for, shown under its slot.
_SHEET_ROLES = (
    "1 — ҳужжат нусхаси",
    "2 — таржима матни",
    "3 — нотариус ўзи тўлдиради",
)


def _desktop() -> Path:
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.exists():
            return candidate
    return Path.home()


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

        blanks = QHBoxLayout()
        blanks.addWidget(QLabel("Бланкалар:"))
        self._blank_labels: list[QLabel] = []
        for index in range(1, 4):
            blanks.addWidget(self._blank_slot(index), stretch=1)
        root.addLayout(blanks)

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
            "Учта бланка бир марта юкланади ва сақланиб қолади. Битта PDF, уч "
            "саҳифа: 1 — ҳужжат нусхаси, рангсиз оқ-қора, ҲАҚИҚИЙ ЎЛЧАМИДА "
            "варақнинг марказида (паспорт 125×88 мм, пластик карта 85.6×54 мм); "
            "олди-орқаси бир варақда, устма-уст; 2 — таржима; 3 — бўш, нотариус "
            "ўзи тўлдиради. Таржима Word бўлиб ҳам сақланади."
        )
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

        self._refresh_blanks()

    # ---------------------------------------------------------- blanks
    def _blank_slot(self, index: int) -> QWidget:
        """One sheet: what is loaded, a button to load it, a button to clear."""
        box = QWidget()
        column = QVBoxLayout(box)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)

        state = QLabel()
        state.setWordWrap(True)
        state.setToolTip(_SHEET_ROLES[index - 1])
        column.addWidget(state)
        self._blank_labels.append(state)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        load = QPushButton(f"➕ {index}-бланка")
        load.setToolTip(_SHEET_ROLES[index - 1])
        load.clicked.connect(lambda _=False, i=index: self._load_blank(i))
        buttons.addWidget(load, stretch=1)
        clear = QPushButton("✕")
        clear.setFixedWidth(28)
        clear.setToolTip("Бу бланкани олиб ташлаш")
        clear.clicked.connect(lambda _=False, i=index: self._clear_blank(i))
        buttons.addWidget(clear)
        column.addLayout(buttons)
        return box

    def _refresh_blanks(self) -> None:
        for index, blank in enumerate(self._svc.blanks(), 1):
            label = self._blank_labels[index - 1]
            role = _SHEET_ROLES[index - 1]
            if blank is None:
                label.setText(f"⛔ {role} — юкланмаган")
                label.setStyleSheet("color:#c08a3e;")
            else:
                label.setText(f"✅ {role}\n{blank.name}")
                label.setStyleSheet("color:#8a94a3;")

    def _load_blank(self, index: int) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"{index}-бланка (бўш варақ)", str(_desktop()), _BLANK_FILTER)
        if not path:
            return
        try:
            self._svc.set_blank(index, Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._refresh_blanks()
        self._status.setText(f"✅ {index}-бланка юкланди: {Path(path).name}")

    def _clear_blank(self, index: int) -> None:
        self._svc.clear_blank(index)
        self._refresh_blanks()
        self._status.setText(f"🗑 {index}-бланка олиб ташланди.")

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
            return self._svc.translate(images, doc_type=doc_type,
                                       form_date=form_date)

        missing = [str(i) for i, blank in enumerate(self._svc.blanks(), 1)
                   if blank is None]
        self._run.setEnabled(False)
        self._status.setText(
            "⏳ AI ҳужжатни ўқияпти ва таржима қиляпти…"
            + (f"  ⚠️ Юкланмаган бланка: {', '.join(missing)} — "
               "ўша саҳифа оқ варақда чиқади." if missing else ""))
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
