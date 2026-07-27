"""ХОСТЕЛ screen — arrival notification for hostel-hosted workers.

Same flow as Registration: pick a hostel, upload passport + patent, set the
stay dates → PDF. Hostels are added inline: name, address parts, host ФИО,
organisation name and ИНН — the program prints them onto the bundled hostel
blank (Times New Roman 10) to make that hostel's template, or an already
filled template PDF can be uploaded instead.
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
from src.controllers.hostel_controller import HostelController
from src.domain.registration_address import RegistrationAddress
from src.services.hostel_service import HostelResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)

_FIELDS = [
    ("label", "Nomi (ro'yxatda ko'rinadi, masalan: ХОСТЕЛ ЛУЖСКАЯ 10)"),
    ("internal_code", "Kod (unikal, masalan: luzhskaya10)"),
    ("oblast", "Область / субъект РФ (masalan: САНКТ-ПЕТЕРБУРГ Г)"),
    ("raion", "Район / поселение"),
    ("gorod", "Город (населенный пункт)"),
    ("ulitsa", "Улица"),
    ("dom", "Дом"),
    ("korpus", "Корпус"),
    ("stroenie", "Строение / литера"),
    ("komnata", "Комната / помещение"),
    ("host_fio", "Хозяин (ФИО, masalan: ДЯГИЛЕВА ЮЛИЯ ГЕННАДЬЕВНА)"),
    ("organization_name", "Наименование организации"),
    ("inn", "ИНН"),
]


class AddHostelDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yangi xostel / Новый хостел")
        self.setMinimumWidth(580)
        self._template: Path | None = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        self._edits: dict[str, QLineEdit] = {}
        for key, label in _FIELDS:
            e = QLineEdit()
            form.addRow(label, e)
            self._edits[key] = e
        outer.addLayout(form)

        hint = QLabel(
            "Jadvalni to'ldirsangiz — shablon avtomatik yasaladi (Times New Roman 10).\n"
            "Yoki tayyor to'ldirilgan xostel shabloni PDF yuklang:"
        )
        hint.setStyleSheet("color:#8a94a3;")
        outer.addWidget(hint)

        pick = QHBoxLayout()
        self._tpl_label = QLabel("Tayyor shablon tanlanmagan (ixtiyoriy)")
        btn = QPushButton("Tayyor shablon…")
        btn.clicked.connect(self._pick_template)
        pick.addWidget(self._tpl_label, stretch=1)
        pick.addWidget(btn)
        outer.addLayout(pick)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _pick_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Xostel shabloni PDF", "", "PDF (*.pdf)")
        if path:
            self._template = Path(path)
            self._tpl_label.setText(f"✓ {Path(path).name}")

    def build(self) -> tuple[RegistrationAddress, Path | None]:
        v = {k: e.text().strip() for k, e in self._edits.items()}
        summary = ", ".join(
            x for x in (
                v["oblast"], v["raion"], v["gorod"], v["ulitsa"],
                f"д. {v['dom']}" if v["dom"] else "",
                f"к. {v['korpus']}" if v["korpus"] else "",
                f"стр. {v['stroenie']}" if v["stroenie"] else "",
                f"ком. {v['komnata']}" if v["komnata"] else "",
            ) if x
        )
        address = RegistrationAddress(
            label=v["label"] or summary or "Xostel",
            internal_code=v["internal_code"] or "hostel",
            address_text=summary or "-",
            host_fio=v["host_fio"] or "-",
            kind="hostel",
            oblast=v["oblast"] or None, raion=v["raion"] or None,
            gorod=v["gorod"] or None, ulitsa=v["ulitsa"] or None,
            dom=v["dom"] or None, korpus=v["korpus"] or None,
            stroenie=v["stroenie"] or None, komnata=v["komnata"] or None,
            organization_name=v["organization_name"] or None, inn=v["inn"] or None,
            template_path=self._template or Path("missing.pdf"),
        )
        return address, self._template


class HostelView(QWidget):
    def __init__(self, controller: HostelController) -> None:
        super().__init__()
        self._c = controller

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("ХОСТЕЛ — Уведомление о прибытии")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        self._hostel = QComboBox()
        self._reload()
        row.addWidget(QLabel("Xostel:"))
        row.addWidget(self._hostel, stretch=2)

        add = QPushButton("+ Yangi xostel")
        add.clicked.connect(self._add)
        row.addWidget(add)
        rm = QPushButton("🗑")
        rm.setToolTip("Tanlangan xostelni ro'yxatdan o'chirish")
        rm.setFixedWidth(40)
        rm.clicked.connect(self._remove)
        row.addWidget(rm)
        root.addLayout(row)

        dates = QHBoxLayout()
        self._start = QDateEdit()
        self._start.setDisplayFormat("dd.MM.yyyy")
        self._start.setDate(QDate.currentDate())
        self._start.setCalendarPopup(True)
        dates.addWidget(QLabel("Boshlanishi:"))
        dates.addWidget(self._start)
        self._expiry = QDateEdit()
        self._expiry.setDisplayFormat("dd.MM.yyyy")
        self._expiry.setDate(QDate.currentDate().addDays(90))
        self._expiry.setCalendarPopup(True)
        dates.addWidget(QLabel("Tugashi:"))
        dates.addWidget(self._expiry)
        dates.addStretch(1)
        root.addLayout(dates)

        up = QHBoxLayout()
        up.setSpacing(12)
        self._dz_passport = DropZone("🛂", "Паспорт")
        self._dz_patent = DropZone("📄", "Патент (олд)")
        self._dz_patent_back = DropZone("🔄", "Патент (орқа)")
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            up.addWidget(dz, stretch=1)
        root.addLayout(up)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (Хостел)")
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
        current = self._hostel.currentText()
        self._reload()
        idx = self._hostel.findText(current)
        if idx >= 0:
            self._hostel.setCurrentIndex(idx)
        self._status.setText(self._hint())

    def _reload(self) -> None:
        self._hostel.clear()
        self._items = self._c.addresses()
        for a in self._items:
            self._hostel.addItem(a.label)

    def _selected(self):
        idx = self._hostel.currentIndex()
        return self._items[idx] if 0 <= idx < len(self._items) else None

    def _expiry_date(self) -> date:
        q = self._expiry.date()
        return date(q.year(), q.month(), q.day())

    def _start_date(self) -> date:
        q = self._start.date()
        return date(q.year(), q.month(), q.day())

    def _hint(self) -> str:
        if not self._items:
            return "Xostel qo'shilmagan — «+ Yangi xostel» tugmasini bosing."
        if self._c.ai_available():
            return "AI tayyor. Pasport + patent rasmlarini yuklang."
        return "AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting."

    # ------------------------------------------------------------------
    def _add(self) -> None:
        dialog = AddHostelDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        address, template = dialog.build()
        try:
            self._c.add_address(address, template)
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        except Exception as exc:  # noqa: BLE001 - surface to the user
            QMessageBox.warning(self, "Xato", str(exc))
            return
        self.refresh()
        self._hostel.setCurrentIndex(self._hostel.count() - 1)

    def _remove(self) -> None:
        address = self._selected()
        if address is None:
            return
        confirm = QMessageBox.question(
            self, "O'chirish", f"«{address.label}» ro'yxatdan olinsinmi?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._c.archive_address(address.id)
        self.refresh()

    def _run_ai(self) -> None:
        address = self._selected()
        if address is None:
            self._warn("Avval xostel tanlang yoki qo'shing.")
            return
        if not self._c.ai_available():
            self._warn("AI kaliti yo'q. Sozlamalarga Gemini kalitini kiriting.")
            return
        if self._dz_passport.path is None:
            self._warn("Pasport rasmini yuklang.")
            return

        passport = self._c.read_image(self._dz_passport.path)
        patent = self._c.read_image(self._dz_patent.path) if self._dz_patent.path else None
        back = (self._c.read_image(self._dz_patent_back.path)
                if self._dz_patent_back.path else None)
        expiry = self._expiry_date()
        start = self._start_date()
        self._busy("AI o'qiyapti va xostel PDF yaratyapti…")
        run_async(
            self._c.generate_from_images, address, passport, patent, back,
            registration_expiry=expiry, registration_start=start,
            on_success=self._done, on_error=self._failed,
        )

    # ------------------------------------------------------------------
    def _busy(self, msg: str) -> None:
        self._run.setEnabled(False)
        self._status.setText("⏳ " + msg)
        self._progress.start(msg)

    def _done(self, result: HostelResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            dz.clear()
        from src.ui.widgets.save_to import ask_save_dir

        saved = ask_save_dir(self, [result.pdf_path])
        extra = f" → {saved}" if saved else ""
        self._status.setText(f"✅ Tayyor: {result.pdf_path.name}{extra}")
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"Xostel PDF yaratildi:\n{result.pdf_path}")
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
