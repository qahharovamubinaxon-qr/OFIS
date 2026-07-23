"""Manual-fill dialog — the offline fallback. A labeled table of the worker's
fields (marks 1–10, 12, 16); each row says what to type. Returns a flat dict for
``build_employee``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.services.manual_entry import MANUAL_FIELDS


class ManualFillDialog(QDialog):
    def __init__(self, lang: str = "ru", prefill: dict[str, str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Qo'lda to'ldirish / Ручной ввод")
        self.setMinimumWidth(520)
        prefill = prefill or {}

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(10)

        self._edits: dict[str, QLineEdit] = {}
        for f in MANUAL_FIELDS:
            edit = QLineEdit(prefill.get(f.key, ""))
            edit.setPlaceholderText("ДД.ММ.ГГГГ" if f.is_date else "")
            label = f.label_uz if lang == "uz" else f.label_ru
            form.addRow(label, edit)
            self._edits[f.key] = edit

        scroll.setWidget(body)
        outer.addWidget(scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def values(self) -> dict[str, str]:
        return {k: e.text().strip() for k, e in self._edits.items()}
