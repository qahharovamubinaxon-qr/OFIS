"""Регистрация screen — «Уведомление о прибытии».

Top: address picker (+ add new address) + registration-expiry date.
Upload passport + patent (front/back) → RUN. The address block and host ФИО are
pre-printed on each address's template; the program fills only the worker boxes
and the two expiry dates. Generation runs on a worker thread.
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
from src.controllers.registration_controller import RegistrationController
from src.domain.registration_address import RegistrationAddress
from src.services.registration_address_service import RegistrationAddressService
from src.services.registration_service import RegistrationResult
from src.ui.widgets.drop_zone import DropZone

log = get_logger(__name__)

_FIELDS = [
    ("label", "Nomi / Название (masalan: 5-Я ПАРКОВАЯ 55-55)"),
    ("internal_code", "Kod (unikal, masalan: parkovaya55)"),
    ("address_text", "Manzil (ro'yxatda ko'rinadi)"),
    ("host_fio", "Qabul qiluvchi FIO (ПОПОВ ВЛАДИМИР ГЕННАДЬЕВИЧ)"),
]


class AddAddressDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yangi manzil / Новый адрес")
        self.setMinimumWidth(500)
        self._template: Path | None = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        self._edits: dict[str, QLineEdit] = {}
        for key, label in _FIELDS:
            e = QLineEdit()
            form.addRow(label, e)
            self._edits[key] = e
        outer.addLayout(form)

        pick = QHBoxLayout()
        self._tpl_label = QLabel("Shablon (to'ldirilgan bo'sh PDF) tanlanmagan")
        btn = QPushButton("Shablon tanlash…")
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
        path, _ = QFileDialog.getOpenFileName(self, "Registratsiya shabloni PDF", "", "PDF (*.pdf)")
        if path:
            self._template = Path(path)
            self._tpl_label.setText(f"✓ {Path(path).name}")

    def build(self) -> tuple[RegistrationAddress, Path | None]:
        v = {k: e.text().strip() for k, e in self._edits.items()}
        address = RegistrationAddress(
            label=v["label"] or "Manzil",
            internal_code=v["internal_code"] or "addr",
            address_text=v["address_text"] or "-",
            host_fio=v["host_fio"] or "-",
            template_path=self._template or Path("missing.pdf"),
        )
        return address, self._template


class RegistrationView(QWidget):
    def __init__(
        self, controller: RegistrationController, addresses: RegistrationAddressService
    ) -> None:
        super().__init__()
        self._c = controller
        self._addresses_service = addresses

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("Ro'yxatga olish / Регистрация")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- address + registration expiry ------------------------------
        row = QHBoxLayout()
        self._address = QComboBox()
        self._reload_addresses()
        row.addWidget(QLabel("Manzil:"))
        row.addWidget(self._address, stretch=2)

        add = QPushButton("+ Yangi manzil")
        add.clicked.connect(self._add_address)
        row.addWidget(add)

        self._expiry = QDateEdit()
        self._expiry.setDisplayFormat("dd.MM.yyyy")
        self._expiry.setDate(QDate.currentDate().addDays(90))
        self._expiry.setCalendarPopup(True)
        row.addWidget(QLabel("Ro'yxat tugashi:"))
        row.addWidget(self._expiry)
        root.addLayout(row)

        # -- uploads ----------------------------------------------------
        up = QHBoxLayout()
        up.setSpacing(12)
        self._dz_passport = DropZone("🛂", "Паспорт")
        self._dz_patent = DropZone("📄", "Патент (олд)")
        self._dz_patent_back = DropZone("🔄", "Патент (орқа)")
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            up.addWidget(dz, stretch=1)
        root.addLayout(up)

        # -- actions ----------------------------------------------------
        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (Регистрация)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._run_ai)
        actions.addWidget(self._run)
        actions.addStretch(1)
        root.addLayout(actions)

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
        current = self._address.currentText()
        self._reload_addresses()
        idx = self._address.findText(current)
        if idx >= 0:
            self._address.setCurrentIndex(idx)
        self._status.setText(self._hint())

    def _reload_addresses(self) -> None:
        self._address.clear()
        self._addresses = self._c.addresses()
        for a in self._addresses:
            self._address.addItem(a.label)

    def _selected_address(self):
        idx = self._address.currentIndex()
        return self._addresses[idx] if 0 <= idx < len(self._addresses) else None

    def _expiry_date(self) -> date:
        q = self._expiry.date()
        return date(q.year(), q.month(), q.day())

    def _hint(self) -> str:
        if not self._addresses:
            return "Avval «+ Yangi manzil» orqali ro'yxat manzili qo'shing."
        if self._c.ai_available():
            return "AI tayyor. Pasport + patent rasmini yuklab, RUN bosing."
        return "AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting."

    # ------------------------------------------------------------------
    def _add_address(self) -> None:
        dialog = AddAddressDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            address, template = dialog.build()
            if template is None:
                QMessageBox.warning(self, "Diqqat", "Shablon PDF tanlang.")
                return
            self._addresses_service.create(address, template_source=template)
            self.refresh()
            QMessageBox.information(self, "OK", f"Manzil qo'shildi: {address.label}")
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
        except Exception as exc:  # noqa: BLE001 - surface validation errors to the user
            QMessageBox.warning(self, "Xato", str(exc))

    def _run_ai(self) -> None:
        address = self._selected_address()
        if address is None:
            self._warn("Avval manzil tanlang yoki qo'shing.")
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
        expiry = self._expiry_date()
        self._busy("AI o'qiyapti va registratsiya PDF yaratyapti…")
        run_async(
            self._c.generate_from_images, address, passport, patent, patent_back,
            registration_expiry=expiry,
            on_success=self._done, on_error=self._failed,
        )

    # ------------------------------------------------------------------
    def _busy(self, msg: str) -> None:
        self._run.setEnabled(False)
        self._status.setText("⏳ " + msg)

    def _done(self, result: RegistrationResult) -> None:
        self._run.setEnabled(True)
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            dz.clear()
        self._status.setText(f"✅ Tayyor: {result.pdf_path.name}")
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"Registratsiya PDF yaratildi:\n{result.pdf_path}")
        open_btn = box.addButton("Papkani ochish", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_folder(result.pdf_path.parent)

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
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
