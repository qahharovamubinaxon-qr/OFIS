"""JPG→PDF screen: drop many images, reorder by dragging rows, RUN → one PDF.

The uploaded images appear as a list; the operator drags rows to set the page
order, presses RUN and picks where to save (обзор).
"""

from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from src.common.threading import run_async
from src.ui.widgets.multi_drop import MultiDropZone
from src.ui.widgets.run_progress import RunProgress


def _build_pdf(paths: list[str]) -> bytes:
    from src.services.jpg2pdf_service import build_pdf_from_paths

    return build_pdf_from_paths(paths)


class Jpg2PdfView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("JPG → PDF")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        self._dz = MultiDropZone("Rasmlarni yuklang", limit=50)
        self._dz.changed.connect(self._sync_list)
        row.addWidget(self._dz, stretch=1)

        col = QVBoxLayout()
        col.addWidget(QLabel("Sahifa tartibi (qatorlarni sudrab o'zgartiring):"))
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setIconSize(QPixmap(64, 64).size())
        col.addWidget(self._list, stretch=1)
        btns = QHBoxLayout()
        rm = QPushButton("🗑 Tanlanganni olib tashlash")
        rm.clicked.connect(self._remove_selected)
        clear = QPushButton("✖ Hammasini tozalash")
        clear.clicked.connect(self._clear)
        btns.addWidget(rm)
        btns.addWidget(clear)
        col.addLayout(btns)
        row.addLayout(col, stretch=1)
        root.addLayout(row, stretch=1)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (PDF yasash)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._make_pdf)
        actions.addWidget(self._run)
        actions.addStretch(1)
        root.addLayout(actions)

        self._progress = RunProgress()
        root.addWidget(self._progress)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)
        self._status = QLabel("Rasmlarni yuklang, tartiblang, RUN bosing.")
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

    # ------------------------------------------------------------------
    def _sync_list(self) -> None:
        existing = {self._list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self._list.count())}
        for f in self._dz.files:
            if str(f) in existing:
                continue
            item = QListWidgetItem(f.name)
            item.setData(Qt.ItemDataRole.UserRole, str(f))
            pix = QPixmap(str(f))
            if not pix.isNull():
                item.setIcon(QIcon(pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation)))
            self._list.addItem(item)

    def _remove_selected(self) -> None:
        for item in self._list.selectedItems():
            self._list.takeItem(self._list.row(item))

    def _clear(self) -> None:
        self._list.clear()
        self._dz.clear_files()

    def _make_pdf(self) -> None:
        paths = [self._list.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self._list.count())]
        if not paths:
            QMessageBox.warning(self, "Diqqat", "Avval rasm yuklang.")
            return
        self._run.setEnabled(False)
        self._progress.start("PDF yasalyapti…")
        run_async(_build_pdf, paths, on_success=self._done, on_error=self._failed)

    def _done(self, pdf_bytes: bytes) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        path, _ = QFileDialog.getSaveFileName(self, "PDF ni saqlash",
                                              "rasm_pdf.pdf", "PDF (*.pdf)")
        if not path:
            self._status.setText("Bekor qilindi.")
            return
        Path(path).write_bytes(pdf_bytes)
        self._status.setText(f"✅ Saqlandi: {path}")

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        QMessageBox.warning(self, "Xato", str(error))
