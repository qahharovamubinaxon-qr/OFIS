"""Archive + Search — list generated documents, filter by surname/name/№,
double-click to open the PDF. One view serves both nav entries.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.database.repositories.generated_repo import GeneratedRepository


class ArchiveView(QWidget):
    def __init__(self, generated: GeneratedRepository, title: str = "Arxiv / Архив") -> None:
        super().__init__()
        self._generated = generated

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        header = QLabel(title)
        header.setObjectName("viewTitle")
        root.addWidget(header)

        search_row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("Familiya, ism yoki № bo'yicha qidirish…")
        self._query.textChanged.connect(self._on_search)
        refresh = QPushButton("↻")
        refresh.clicked.connect(self.refresh)
        search_row.addWidget(self._query, stretch=1)
        search_row.addWidget(refresh)
        root.addLayout(search_row)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._open)
        root.addWidget(self._list, stretch=1)

        hint = QLabel("PDF ochish uchun ustiga ikki marta bosing.")
        hint.setStyleSheet("color:#8a94a3;")
        root.addWidget(hint)

        self.refresh()

    def refresh(self) -> None:
        self._populate(self._generated.recent(200))

    def _on_search(self, text: str) -> None:
        records = self._generated.search(text) if text.strip() else self._generated.recent(200)
        self._populate(records)

    def _populate(self, records) -> None:
        self._list.clear()
        for r in records:
            item = QListWidgetItem(
                f"№{r.reg_number}  ·  {r.full_name}  ·  {r.citizenship}  ·  {r.company_name}  ·  {r.form_date}"
            )
            item.setData(256, r.pdf_path)  # Qt.UserRole
            self._list.addItem(item)

    def _open(self, item: QListWidgetItem) -> None:
        path = Path(item.data(256))
        if not path.exists():
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(path)])  # noqa: S603,S607
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
        except OSError:
            pass
