"""РАСМ-ФОТО screen — document photo maker.

Upload (or drag) any worker photo → the program straightens the head, crops to
document 3×4, cleans the background to white and shows the result next to the
upload box. The ready photo can be saved to a file or copied to the clipboard.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.logging import get_logger
from src.common.threading import run_async
from src.services.photo_service import PhotoResult, PhotoService
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)


class PhotoView(QWidget):
    def __init__(self, service: PhotoService) -> None:
        super().__init__()
        self._service = service
        self._result_png: bytes | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("РАСМ-ФОТО — Документ учун 3×4")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(16)

        self._dz = DropZone("🖼️", "Rasm yuklang (istalgan foto)")
        self._dz.changed.connect(self._on_photo)
        row.addWidget(self._dz, stretch=1)

        arrow = QLabel("→")
        arrow.setStyleSheet("font-size: 28px; color:#8a94a3;")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(arrow)

        right = QVBoxLayout()
        self._preview = QLabel("Tayyor rasm shu yerda ko'rinadi")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(240, 320)
        self._preview.setStyleSheet(
            "border: 2px dashed #3a4354; border-radius: 12px; color:#8a94a3;"
        )
        right.addWidget(self._preview, stretch=1)

        btns = QHBoxLayout()
        self._save = QPushButton("💾 Saqlash")
        self._save.clicked.connect(self._save_photo)
        self._copy = QPushButton("📋 Copy")
        self._copy.clicked.connect(self._copy_photo)
        for b in (self._save, self._copy):
            b.setEnabled(False)
            btns.addWidget(b)
        right.addLayout(btns)
        row.addLayout(right, stretch=1)
        root.addLayout(row, stretch=1)

        self._progress = RunProgress()
        root.addWidget(self._progress)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel("Rasm yuklang — dastur 3×4 qilib, fonini tozalab beradi.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

    # ------------------------------------------------------------------
    def _on_photo(self) -> None:
        if self._dz.path is None:
            return
        data = Path(self._dz.path).read_bytes()
        self._save.setEnabled(False)
        self._copy.setEnabled(False)
        self._status.setText("⏳ Rasm ishlanyapti…")
        self._progress.start("Rasm ishlanyapti…")
        run_async(self._service.process, data,
                  on_success=self._done, on_error=self._failed)

    def _done(self, result: PhotoResult) -> None:
        self._progress.finish()
        self._result_png = result.png
        img = QImage.fromData(result.png, "PNG")
        pix = QPixmap.fromImage(img).scaled(
            self._preview.width(), self._preview.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview.setPixmap(pix)
        self._save.setEnabled(True)
        self._copy.setEnabled(True)
        if result.face_found:
            self._status.setText("✅ Tayyor: 3×4, fon oq, bosh tekislangan. Saqlang yoki Copy qiling.")
        else:
            self._status.setText("⚠️ Yuz topilmadi — rasm faqat 3×4 qilib kesildi.")

    def _failed(self, error: Exception) -> None:
        self._progress.fail()
        self._status.setText("❌ " + str(error))
        QMessageBox.warning(self, "Xato", str(error))

    # ------------------------------------------------------------------
    def _save_photo(self) -> None:
        if not self._result_png:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Rasmni saqlash", "photo_3x4.png", "PNG (*.png);;JPEG (*.jpg)"
        )
        if not path:
            return
        if path.lower().endswith((".jpg", ".jpeg")):
            img = QImage.fromData(self._result_png, "PNG")
            img.save(path, "JPEG", 95)
        else:
            Path(path).write_bytes(self._result_png)
        self._status.setText(f"✅ Saqlandi: {path}")

    def _copy_photo(self) -> None:
        if not self._result_png:
            return
        QApplication.clipboard().setImage(QImage.fromData(self._result_png, "PNG"))
        self._status.setText("✅ Rasm buferga nusxalandi (Ctrl+V bilan qo'ying).")
