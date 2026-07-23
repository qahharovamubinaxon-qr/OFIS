"""Companies screen — list stored companies and add a new one.

Adding a company copies its blank template into templates/<code>/ and stores the
record; no code change is ever needed for a new company (all share one mapping).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.domain.company import Company
from src.domain.enums import EmployerType
from src.services.company_service import CompanyService

_FIELDS = [
    ("name", "Название / Nomi"),
    ("internal_code", "Внутренний код (уникальный)"),
    ("inn", "ИНН"),
    ("ogrn", "ОГРН / ОГРНИП"),
    ("okved", "ОКВЭД"),
    ("address_index", "Индекс"),
    ("address_text", "Адрес"),
    ("director_fio", "ФИО директора"),
]


class AddCompanyDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yangi firma / Новая компания")
        self.setMinimumWidth(480)
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
        self._tpl_label = QLabel("Shablon (bo'sh PDF) tanlanmagan")
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
        path, _ = QFileDialog.getOpenFileName(self, "Bo'sh shablon PDF", "", "PDF (*.pdf)")
        if path:
            self._template = Path(path)
            self._tpl_label.setText(f"✓ {Path(path).name}")

    def build(self) -> tuple[Company, Path | None]:
        v = {k: e.text().strip() for k, e in self._edits.items()}
        company = Company(
            name=v["name"], internal_code=v["internal_code"], employer_type=EmployerType.IP,
            okved=v["okved"] or "00.00", ogrn=v["ogrn"] or "0000000000000",
            inn=v["inn"] or "0000000000", address_index=v["address_index"] or "000000",
            address_text=v["address_text"] or "-", director_fio=v["director_fio"] or "-",
            template_path=self._template or Path("missing.pdf"),
        )
        return company, self._template


class CompaniesView(QWidget):
    def __init__(self, service: CompanyService) -> None:
        super().__init__()
        self._service = service

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Firmalar / Компании")
        title.setObjectName("viewTitle")
        header.addWidget(title, stretch=1)
        add = QPushButton("+ Yangi firma")
        add.clicked.connect(self._add)
        header.addWidget(add)
        root.addLayout(header)

        self._list = QListWidget()
        root.addWidget(self._list, stretch=1)
        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        for c in self._service.list():
            self._list.addItem(f"{c.name}   ·   ИНН {c.inn}   ·   {c.internal_code}")

    def _add(self) -> None:
        dialog = AddCompanyDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            company, template = dialog.build()
            if template is None:
                QMessageBox.warning(self, "Diqqat", "Shablon PDF tanlang.")
                return
            self._service.create(company, template_source=template)
            self.refresh()
            QMessageBox.information(self, "OK", f"Firma qo'shildi: {company.name}")
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
        except Exception as exc:  # noqa: BLE001 - surface validation errors to the user
            QMessageBox.warning(self, "Xato", str(exc))
