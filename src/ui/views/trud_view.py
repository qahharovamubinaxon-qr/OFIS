"""Трудовой-Уведомления screen.

Pick a firm (add/delete inline — a firm either uploads TWO templates, трудовой +
уведомление, or is typed in by its requisites and the program writes the pair
itself), upload passport + patent (front/back), pick date + должность,
RUN → two documents (договор + уведомление), saved by surname.
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
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.common.threading import run_async
from src.controllers.trud_controller import TrudController
from src.domain.enums import LegalForm
from src.domain.firm_details import FirmDetails
from src.services.trud_service import DEFAULT_TRUD_PROFESSION, TrudResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)


#: Requisites of a firm typed in by hand: attribute · label · placeholder.
MANUAL_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("name", "To'liq nomi *", 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "СФЕРА"'),
    ("short_name", "Qisqa nomi", 'ООО "СФЕРА"'),
    ("inn", "ИНН", "7743447264"),
    ("kpp", "КПП (ИП da yo'q)", "774301001"),
    ("ogrn", "ОГРН / ОГРНИП", "1247700301133"),
    ("okved", "ОКВЭД", "42.99"),
    ("address", "Yuridik manzil", "141008, обл. Московская, г. Мытищи, ул. Мира, д. 37"),
    ("district", "Rayon / shahar", "г.о. Мытищи"),
    ("mvd_office", "МВД bo'limi", "ОПВМ ОМВД РОССИИ ПО Г.О. МЫТИЩИ"),
    ("director_position", "Direktor lavozimi", "Генеральный директор"),
    ("director", "Direktor Ф.И.О.", "Нуар А. В."),
    ("phone", "Telefon", "+7 (812) 740 63 70"),
)


def _row_widget(*widgets) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    for widget, stretch in widgets:
        row.addWidget(widget, stretch=stretch)
    return holder


class ManualFirmForm(QWidget):
    """Type a firm's requisites; the program writes both Word templates itself.

    For a firm that never handed over a Word file — everything the two
    documents need that is not the worker's own data.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.stamp: Path | None = None
        form = QFormLayout(self)

        self.legal_form = QComboBox()
        self.legal_form.addItem("ООО / юридическое лицо", LegalForm.OOO)
        self.legal_form.addItem("ИП / индивидуальный предприниматель", LegalForm.IP)
        form.addRow("Turi", self.legal_form)

        self.fields: dict[str, QLineEdit] = {}
        for key, label, hint in MANUAL_FIELDS:
            edit = QLineEdit()
            edit.setPlaceholderText(hint)
            if key == "director_position":
                edit.setText("Генеральный директор")
            self.fields[key] = edit
            form.addRow(label, edit)

        self._stamp_label = QLabel("tanlanmagan")
        pick = QPushButton("Печать (PNG)…")
        pick.clicked.connect(self._pick_stamp)
        form.addRow("Печать", _row_widget((self._stamp_label, 1), (pick, 0)))

        self.legal_form.currentIndexChanged.connect(self._form_changed)
        self._form_changed()

    def _form_changed(self) -> None:
        """An ИП has no КПП — clear the box rather than reject it on save."""
        is_ip = self.chosen_form() is LegalForm.IP
        kpp = self.fields["kpp"]
        if is_ip:
            kpp.clear()
        kpp.setEnabled(not is_ip)
        self.fields["director_position"].setEnabled(not is_ip)
        self.fields["ogrn"].setPlaceholderText(
            "321774600123456" if is_ip else "1247700301133")

    def _pick_stamp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Печать (PNG)", "", "PNG (*.png)")
        if path:
            self.stamp = Path(path)
            self._stamp_label.setText(f"✓ {Path(path).name}")

    def chosen_form(self) -> LegalForm:
        """Qt hands the item data back as a plain str, so re-read the member."""
        return LegalForm(self.legal_form.currentData())

    def details(self) -> FirmDetails:
        """Raises ``ValueError`` with a readable message when a value is wrong."""
        from pydantic import ValidationError as PydanticError

        values = {key: edit.text().strip() for key, edit in self.fields.items()}
        try:
            return FirmDetails(legal_form=self.chosen_form(),
                               stamp_path=self.stamp, **values)
        except PydanticError as exc:
            raise ValueError("\n".join(
                e["msg"].removeprefix("Value error, ") for e in exc.errors())
            ) from exc


class AddTrudFirmDialog(QDialog):
    """Two ways in: upload the firm's own Word/PDF pair, or type its requisites."""

    UPLOAD, MANUAL = 0, 1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yangi firma / Новая фирма (Трудовой)")
        self.setMinimumWidth(560)
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

        uploaded = QWidget()
        upload_box = QVBoxLayout(uploaded)

        self._trud_label = QLabel("Трудовой шаблон tanlanmagan")
        btn1 = QPushButton("Трудовой шаблон…")
        btn1.clicked.connect(lambda: self._pick("trud"))
        upload_box.addWidget(_row_widget((self._trud_label, 1), (btn1, 0)))

        self._uved_label = QLabel("Уведомление шаблон tanlanmagan")
        btn2 = QPushButton("Уведомление шаблон…")
        btn2.clicked.connect(lambda: self._pick("uved"))
        upload_box.addWidget(_row_widget((self._uved_label, 1), (btn2, 0)))

        self._hod_label = QLabel("Ходатайство шаблон (ixtiyoriy)")
        btn3 = QPushButton("Ходатайство шаблон…")
        btn3.clicked.connect(lambda: self._pick("hod"))
        upload_box.addWidget(_row_widget((self._hod_label, 1), (btn3, 0)))
        upload_box.addStretch(1)

        self.manual = ManualFirmForm()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.manual)

        self.tabs = QTabWidget()
        self.tabs.addTab(uploaded, "Shablon yuklash")
        self.tabs.addTab(scroll, "Qo'lda kiritish")
        outer.addWidget(self.tabs, stretch=1)

        hint = QLabel("Qo'lda kiritilsa — уведомление va трудовой договорни "
                      "programma o'zi yozadi, shablon kerak emas.")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    @property
    def mode(self) -> int:
        return self.tabs.currentIndex()

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
            return ("Avval «+ Yangi firma» orqali firma qo'shing — shablon "
                    "yuklang yoki rekvizitlarni qo'lda kiriting.")
        if self._c.ai_available():
            return "AI tayyor. Pasport + patent yuklab, RUN bosing — 2 ta PDF tayyorlanadi."
        return "AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting."

    # ------------------------------------------------------------------
    def _add_firm(self) -> None:
        dialog = AddTrudFirmDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, code, trud_tpl, uved_tpl, hod_tpl = dialog.values()
        manual = dialog.mode == AddTrudFirmDialog.MANUAL
        if not code:
            QMessageBox.warning(self, "Diqqat", "Firma kodi kerak.")
            return
        if not manual and (not name or trud_tpl is None or uved_tpl is None):
            QMessageBox.warning(self, "Diqqat",
                                "Nomi, kod va IKKALA shablon ham kerak.")
            return
        try:
            if manual:
                details = dialog.manual.details()
                firm = self._c.add_firm_manual(details, code)
            else:
                firm = self._c.add_firm(name, code, trud_tpl, uved_tpl, hod_tpl)
            self.refresh()
        except ValueError as exc:            # a requisite typed wrong
            QMessageBox.warning(self, "Xato", str(exc))
            return
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Xato", str(exc))
            return
        if manual:
            # nothing to study: the program wrote both templates itself and
            # knows exactly where every value goes
            note = ("✅ Firma qo'shildi. Уведомление va трудовой договор "
                    "programma tomonidan yozildi — shablon kerak emas.")
            self._status.setText(note)
            QMessageBox.information(self, "Tayyor", note)
            return
        self._study_uved(firm)

    def _study_uved(self, firm) -> None:
        """Read the new firm's templates so both documents fill the right gaps.

        Every firm's Госуслуги blank is laid out differently — that is what
        put a worker's surname on the «Отчество» line — and a PDF contract
        leaves its gaps wherever the firm's Word document happened to.
        """
        self._busy("Бланкалар ўрганилаяпти…")
        run_async(self._c.study_templates, firm,
                  on_success=self._studied, on_error=self._study_failed)

    def _studied(self, studies: dict) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        lines, warned = [], False
        for label, key in (("Уведомление", "uved"), ("Трудовой договор", "trud")):
            study = studies.get(key)
            if study is None:
                lines.append(f"ℹ️ {label}: Word файл — ўрганиш керак эмас, "
                             "матн бўйича тўлдирилади.")
                continue
            if study.ok:
                lines.append(f"✅ {label}: {len(study.fields)} та жой топилди.")
                if study.missing:
                    lines.append("   ⚠️ Топилмагани: " + ", ".join(study.missing)
                                 + " — бу жойлар бўш қолади.")
                    warned = True
            else:
                lines.append(f"⚠️ {label}: етарли жой топилмади — эски "
                             "жойлашув ишлатилади. Файлни текшириб қайта юкланг.")
                warned = True
        note = "\n".join(lines)
        self._status.setText(note)
        if warned:
            QMessageBox.warning(self, "Diqqat", note)
        else:
            QMessageBox.information(self, "Tayyor", note)

    def _study_failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        msg = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("⚠️ Бланкалар ўрганилмади: " + msg)
        QMessageBox.warning(self, "Diqqat", "Бланкалар ўрганилмади:\n" + msg)

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
        note = f"✅ Tayyor: {result.trud_path.name} + {result.uved_path.name}{extra}"
        if result.notes:
            # the PDF was read back and something did not check out — the
            # operator hears it now, not at the ministry counter
            note += "\n⚠️ " + "\n⚠️ ".join(result.notes)
        self._status.setText(note)
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
