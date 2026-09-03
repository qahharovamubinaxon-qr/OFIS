"""СФЕРА screen — Удостоверение + Протокол for the training centre.

Pick a profession (сфера), a date, upload the student photo + passport →
RUN. Produces a 2-page PDF (certificate + protocol) named by surname. New
professions can be added inline.

The ФИО boxes override whatever the passport is read as, and filling them in
lets a certificate be made with no passport at all.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.common.threading import run_async
from src.controllers.svera_controller import SveraController
from src.services.svera_service import SveraResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)


class AddProfessionDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yangi soha / Новая профессия")
        self.setMinimumWidth(440)
        outer = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit()
        self._note = QLineEdit()
        self._grade = QSpinBox()
        self._grade.setRange(1, 8)
        self._grade.setValue(5)
        form.addRow("Nomi / Название", self._name)
        form.addRow("Izoh (ixtiyoriy, masalan: аргонодуговая)", self._note)
        form.addRow("Разряд", self._grade)
        outer.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def values(self) -> tuple[str, str | None, int]:
        return self._name.text().strip(), self._note.text().strip() or None, self._grade.value()


class SveraView(QWidget):
    def __init__(self, controller: SveraController) -> None:
        super().__init__()
        self._c = controller

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("СФЕРА — Удостоверение + Протокол")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- profession + date ------------------------------------------
        row = QHBoxLayout()
        self._prof = QComboBox()
        self._reload_professions()
        row.addWidget(QLabel("Soha:"))
        row.addWidget(self._prof, stretch=2)
        add = QPushButton("+ Yangi soha")
        add.clicked.connect(self._add_profession)
        row.addWidget(add)

        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(QLabel("Sana:"))
        row.addWidget(self._date)
        root.addLayout(row)

        # -- the student's name -----------------------------------------
        names = QHBoxLayout()
        names.addWidget(QLabel("Ф.И.О.:"))
        self._surname = QLineEdit()
        self._surname.setPlaceholderText("Фамилия")
        self._name = QLineEdit()
        self._name.setPlaceholderText("Исм")
        self._patronymic = QLineEdit()
        self._patronymic.setPlaceholderText("Отчество")
        for w in (self._surname, self._name, self._patronymic):
            names.addWidget(w, stretch=1)
        root.addLayout(names)

        # -- uploads ----------------------------------------------------
        up = QHBoxLayout()
        up.setSpacing(12)
        self._dz_photo = DropZone("🖼️", "O'quvchi rasmi (foto)")
        self._dz_passport = DropZone("🛂", "Паспорт (ихтиёрий)")
        # dropping the passport reads the ФИО straight into the boxes above,
        # for the operator to check before printing
        self._dz_passport.changed.connect(self._on_passport_dropped)
        for dz in (self._dz_photo, self._dz_passport):
            up.addWidget(dz, stretch=1)
        root.addLayout(up)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(400)
        self._settle.timeout.connect(self._read_passport)

        # -- actions ----------------------------------------------------
        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (СФЕРА)")
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

        self._status = QLabel(self._hint())
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        current = self._prof.currentText()
        self._reload_professions()
        idx = self._prof.findText(current)
        if idx >= 0:
            self._prof.setCurrentIndex(idx)
        self._status.setText(self._hint())

    def _reload_professions(self) -> None:
        self._prof.clear()
        self._professions = self._c.professions()
        for p in self._professions:
            label = p.name + (f" ({p.note})" if p.note else "")
            self._prof.addItem(label)

    def _selected_profession(self):
        idx = self._prof.currentIndex()
        return self._professions[idx] if 0 <= idx < len(self._professions) else None

    def _issue_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    def _hint(self) -> str:
        typed = "Ф.И.О. yozsangiz — pasportdan o'qilgani o'rniga o'sha yoziladi."
        if self._c.ai_available():
            return (f"AI tayyor. Keyingi ПО raqami: {self._c.next_po_number()}. "
                    + typed)
        return ("AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting, "
                "yoki pasportsiz Ф.И.О. ni qo'lda yozing.")

    # ------------------------------------------------------------------
    def _add_profession(self) -> None:
        dialog = AddProfessionDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, note, grade = dialog.values()
        if not name:
            QMessageBox.warning(self, "Diqqat", "Soha nomini kiriting.")
            return
        try:
            self._c.add_profession(name, note, grade)
            self.refresh()
            self._prof.setCurrentIndex(self._prof.count() - 1)
        except Exception as exc:  # noqa: BLE001 - surface to the user
            QMessageBox.warning(self, "Xato", str(exc))

    # ------------------------------------------------------------ reading
    def _on_passport_dropped(self) -> None:
        """The (optional) passport landed — read the ФИО into the boxes."""
        if self._dz_passport.path is None or not self._c.ai_available():
            return
        self._settle.start()

    def _read_passport(self) -> None:
        if self._dz_passport.path is None or not self._c.ai_available():
            return
        data = self._c.read_image(self._dz_passport.path)
        self._status.setText("⏳ Паспорт ўқиляпти…")
        self._progress.start("Паспорт ўқиляпти…")
        run_async(self._c.read_passport, data,
                  on_success=self._name_filled, on_error=self._read_failed)

    def _name_filled(self, passport) -> None:
        self._progress.finish()
        self._surname.setText(passport.surname or "")
        self._name.setText(passport.name or "")
        self._patronymic.setText(passport.patronymic or "")
        self._status.setText("✅ Ф.И.О. ўқилди — текширинг, хатоси бўлса "
                             "тўғриланг, кейин RUN.")

    def _read_failed(self, error: Exception) -> None:
        self._progress.finish()
        msg = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText(f"❌ Ўқилмади: {msg}. Ф.И.О. ни қўлда ёзинг.")

    # ------------------------------------------------------------ printing
    def _run_ai(self) -> None:
        profession = self._selected_profession()
        if profession is None:
            self._warn("Avval soha tanlang yoki qo'shing.")
            return
        if self._dz_photo.path is None:
            self._warn("O'quvchi rasmini (foto) yuklang.")
            return

        # the boxes are the single source: the passport, when dropped, has
        # already read its ФИО into them for the operator to check
        surname = self._surname.text().strip()
        name = self._name.text().strip()
        patronymic = self._patronymic.text().strip()
        if not (surname and name):
            self._warn("Ф.И.О. бўш — паспорт юкланг (ўзи ўқийди) ёки қўлда "
                       "камида фамилия ва исмни ёзинг.")
            return

        photo_path = self._dz_photo.path
        issue_date = self._issue_date()
        self._busy("СФЕРА PDF yaratyapti…")
        run_async(
            self._c.generate_from_images, profession, None, photo_path,
            issue_date=issue_date, surname=surname, name=name,
            patronymic=patronymic,
            on_success=self._done, on_error=self._failed,
        )

    # ------------------------------------------------------------------
    def _busy(self, msg: str) -> None:
        self._run.setEnabled(False)
        self._status.setText("⏳ " + msg)
        self._progress.start(msg)

    def _done(self, result: SveraResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        for dz in (self._dz_photo, self._dz_passport):
            dz.clear()
        for field in (self._surname, self._name, self._patronymic):
            field.clear()
        self._status.setText(f"✅ Tayyor: {result.pdf_path.name}  (ПО{result.po_number})")
        from src.ui.widgets.save_to import ask_save_dir

        ask_save_dir(self, [result.pdf_path])
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"СФЕРА PDF yaratildi:\n{result.pdf_path}")
        open_btn = box.addButton("Papkani ochish", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_folder(result.pdf_path.parent)

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        msg = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + msg)
        self._warn(msg)

    def _warn(self, msg: str) -> None:
        QMessageBox.warning(self, "Diqqat", msg)

    @staticmethod
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
