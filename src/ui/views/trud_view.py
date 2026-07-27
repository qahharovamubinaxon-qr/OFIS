"""Трудовой-Уведомления screen.

Pick a firm (add/delete inline — each firm uploads TWO templates: трудовой +
уведомление), upload passport + patent (front/back), pick date + должность,
RUN → two PDFs (договор + уведомление), saved by surname.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
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
from src.common.logging import get_logger
from src.common.threading import run_async
from src.controllers.trud_controller import TrudController
from src.services.trud_service import DEFAULT_TRUD_PROFESSION, TrudResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)


class AddTrudFirmDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yangi firma / Новая фирма (Трудовой)")
        self.setMinimumWidth(520)
        self._trud_tpl: Path | None = None
        self._uved_tpl: Path | None = None
        self._hod_tpl: Path | None = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit()
        self._code = QLineEdit()
        form.addRow("Nomi / Название", self._name)
        form.addRow("Kod (unikal)", self._code)
        outer.addLayout(form)

        self._trud_label = QLabel("Трудовой шаблон tanlanmagan")
        btn1 = QPushButton("Трудовой шаблон…")
        btn1.clicked.connect(lambda: self._pick("trud"))
        row1 = QHBoxLayout()
        row1.addWidget(self._trud_label, stretch=1)
        row1.addWidget(btn1)
        outer.addLayout(row1)

        self._uved_label = QLabel("Уведомление шаблон tanlanmagan")
        btn2 = QPushButton("Уведомление шаблон…")
        btn2.clicked.connect(lambda: self._pick("uved"))
        row2 = QHBoxLayout()
        row2.addWidget(self._uved_label, stretch=1)
        row2.addWidget(btn2)
        outer.addLayout(row2)

        self._hod_label = QLabel("Ходатайство шаблон (ixtiyoriy)")
        btn3 = QPushButton("Ходатайство шаблон…")
        btn3.clicked.connect(lambda: self._pick("hod"))
        row3 = QHBoxLayout()
        row3.addWidget(self._hod_label, stretch=1)
        row3.addWidget(btn3)
        outer.addLayout(row3)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _pick(self, kind: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Shablon (PDF yoki Word)", "", "PDF/Word (*.pdf *.docx)")
        if not path:
            return
        if kind == "trud":
            self._trud_tpl = Path(path)
            self._trud_label.setText(f"✓ {Path(path).name}")
        elif kind == "hod":
            self._hod_tpl = Path(path)
            self._hod_label.setText(f"✓ {Path(path).name}")
        else:
            self._uved_tpl = Path(path)
            self._uved_label.setText(f"✓ {Path(path).name}")

    def values(self):
        return (self._name.text().strip(), self._code.text().strip(),
                self._trud_tpl, self._uved_tpl, self._hod_tpl)


class TrudView(QWidget):
    def __init__(self, controller: TrudController) -> None:
        super().__init__()
        self._c = controller

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("Трудовой — Уведомление")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        self._firm = QComboBox()
        self._reload_firms()
        row.addWidget(QLabel("Фирма:"))
        row.addWidget(self._firm, stretch=2)
        add = QPushButton("+ Yangi firma")
        add.clicked.connect(self._add_firm)
        row.addWidget(add)
        rm = QPushButton("🗑")
        rm.setToolTip("Tanlangan firmani ro'yxatdan o'chirish")
        rm.setFixedWidth(40)
        rm.clicked.connect(self._remove_firm)
        row.addWidget(rm)

        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(QLabel("Дата:"))
        row.addWidget(self._date)
        root.addLayout(row)

        row2 = QHBoxLayout()
        self._profession = QLineEdit(DEFAULT_TRUD_PROFESSION)
        row2.addWidget(QLabel("Должность:"))
        row2.addWidget(self._profession, stretch=1)
        root.addLayout(row2)

        up = QHBoxLayout()
        up.setSpacing(12)
        self._dz_passport = DropZone("🛂", "Паспорт")
        self._dz_patent = DropZone("📄", "Патент (олд)")
        self._dz_patent_back = DropZone("🔄", "Патент (орқа)")
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            up.addWidget(dz, stretch=1)
        root.addLayout(up)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (Трудовой + Уведомление)")
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
        current = self._firm.currentText()
        self._reload_firms()
        idx = self._firm.findText(current)
        if idx >= 0:
            self._firm.setCurrentIndex(idx)
        self._status.setText(self._hint())

    def _reload_firms(self) -> None:
        self._firm.clear()
        self._firms = self._c.firms()
        for f in self._firms:
            self._firm.addItem(f.name)

    def _selected_firm(self):
        idx = self._firm.currentIndex()
        return self._firms[idx] if 0 <= idx < len(self._firms) else None

    def _form_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    def _hint(self) -> str:
        if not self._firms:
            return "Avval «+ Yangi firma» orqali firma qo'shing (2 ta shablon yuklanadi)."
        if self._c.ai_available():
            return "AI tayyor. Pasport + patent yuklab, RUN bosing — 2 ta PDF tayyorlanadi."
        return "AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting."

    # ------------------------------------------------------------------
    def _add_firm(self) -> None:
        dialog = AddTrudFirmDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, code, trud_tpl, uved_tpl, hod_tpl = dialog.values()
        if not name or not code or trud_tpl is None or uved_tpl is None:
            QMessageBox.warning(self, "Diqqat",
                                "Nomi, kod va IKKALA shablon PDF ham kerak.")
            return
        try:
            firm = self._c.add_firm(name, code, trud_tpl, uved_tpl, hod_tpl)
            self.refresh()
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Xato", str(exc))
            return
        self._study_uved(firm)

    def _study_uved(self, firm) -> None:
        """Read the new firm's blank so its уведомление fills in the right rows.

        Every firm's Госуслуги blank is laid out differently, so this is what
        stops a worker's surname landing on the «Отчество» line.
        """
        self._busy("Уведомление бланкаси ўрганилаяпти…")
        run_async(self._c.study_uved, firm,
                  on_success=self._studied, on_error=self._study_failed)

    def _studied(self, study) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        found = len(study.fields)
        if study.ok:
            note = f"✅ Бланка ўрганилди: {found} та майдон топилди."
            if study.missing:
                note += ("\n⚠️ Топилмагани: " + ", ".join(study.missing)
                         + " — бу қаторлар бўш қолади.")
            self._status.setText(note)
            QMessageBox.information(self, "Tayyor", note)
            return
        note = (f"⚠️ Бланкадан фақат {found} та майдон топилди — камлик "
                "қиляпти, шунинг учун эски жойлашув ишлатилади.\n"
                "Бланкани текшириб, қайта юкланг.")
        self._status.setText(note)
        QMessageBox.warning(self, "Diqqat", note)

    def _study_failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        msg = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("⚠️ Бланка ўрганилмади: " + msg)
        QMessageBox.warning(self, "Diqqat", "Бланка ўрганилмади:\n" + msg)

    def _remove_firm(self) -> None:
        firm = self._selected_firm()
        if firm is None:
            return
        if QMessageBox.question(
            self, "O'chirish", f"«{firm.name}» ro'yxatdan o'chirilsinmi?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._c.archive_firm(firm.id)
        self.refresh()

    def _run_ai(self) -> None:
        firm = self._selected_firm()
        if firm is None:
            self._warn("Avval firma tanlang yoki qo'shing.")
            return
        if not self._c.ai_available():
            self._warn("AI kaliti yo'q. Sozlamalarga Gemini kalitini kiriting.")
            return
        if self._dz_passport.path is None:
            self._warn("Pasport rasmini yuklang.")
            return
        passport = self._c.read_image(self._dz_passport.path)
        patent = self._c.read_image(self._dz_patent.path) if self._dz_patent.path else None
        patent_back = (
            self._c.read_image(self._dz_patent_back.path) if self._dz_patent_back.path else None
        )
        profession = self._profession.text().strip() or None
        self._busy("AI o'qiyapti, трудовой + уведомление tayyorlanyapti…")
        run_async(
            self._c.generate_from_images, firm, passport, patent, patent_back,
            form_date=self._form_date(), profession=profession,
            on_success=self._done, on_error=self._failed,
        )

    # ------------------------------------------------------------------
    def _busy(self, msg: str) -> None:
        self._run.setEnabled(False)
        self._status.setText("⏳ " + msg)
        self._progress.start(msg)

    def _done(self, result: TrudResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            dz.clear()
        from src.ui.widgets.save_to import ask_save_dir

        ask_save_dir(self, [x for x in (result.trud_path, result.uved_path,
                                        result.hod_path) if x])
        extra = f" + {result.hod_path.name}" if result.hod_path else ""
        self._status.setText(
            f"✅ Tayyor: {result.trud_path.name} + {result.uved_path.name}{extra}")
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"2 ta PDF yaratildi:\n{result.trud_path.name}\n{result.uved_path.name}")
        open_btn = box.addButton("Papkani ochish", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_folder(result.trud_path.parent)

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
