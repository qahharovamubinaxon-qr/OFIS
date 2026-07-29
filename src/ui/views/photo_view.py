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
    QCheckBox,
    QComboBox,
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
        self._result_pdf: bytes | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("РАСМ-ФОТО — Документ учун 3×4")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Nima kerak:"))
        self._mode = QComboBox()
        self._mode.addItem("🧍 Odam rasmi — 3×4", "photo")
        self._mode.addItem("📄 Hujjat — skan → PDF", "document")
        self._mode.setFixedWidth(210)
        self._mode.setToolTip(
            "«Hujjat» — pasport, prava yoki patentni telefonda suratga oling.\n"
            "Dastur hujjatning chetlarini topib to'g'rilaydi, oq-qora qiladi\n"
            "va sahifa markaziga qo'yib PDF qiladi.")
        self._mode.currentIndexChanged.connect(self._on_mode)
        opts.addWidget(self._mode)

        self._bg_label = QLabel("Fon rangi:")
        opts.addWidget(self._bg_label)
        self._bg = QComboBox()
        for label, key in (("⬜ Oq", "white"), ("◽ Och kulrang", "gray"),
                           ("🟦 Ko'k", "blue"), ("🎬 Studiya", "studio")):
            self._bg.addItem(label, key)
        self._bg.setToolTip(
            "«Studiya» — och kulrang fon, o'rtasi yorug', chetiga qarab "
            "yumshoq qorayadi va yelka ortida mayin soya bo'ladi.\n"
            "Yuzga umuman tegilmaydi: faqat odamning ORQASI bo'yaladi.")
        self._bg.setFixedWidth(180)
        self._bg.currentIndexChanged.connect(self._on_photo)
        opts.addWidget(self._bg)

        self._grey = QCheckBox("Oq-qora")
        self._grey.setChecked(True)
        self._grey.setToolTip("Skaner qilgandek oq-qora. Olib tashlansa rangli qoladi.")
        self._grey.stateChanged.connect(self._on_photo)
        opts.addWidget(self._grey)

        self._reset = QPushButton("🗑 Tozalash")
        self._reset.clicked.connect(self.reset)
        opts.addWidget(self._reset)
        opts.addStretch(1)
        root.addLayout(opts)

        row = QHBoxLayout()
        row.setSpacing(16)

        self._dz = DropZone("🖼️", "Rasm yuklang (istalgan foto)")
        self._dz.changed.connect(self._on_photo)
        row.addWidget(self._dz, stretch=1)

        self._dz_doc = DropZone("📄", "Hujjat rasmlarini yuklang", multiple=True)
        self._dz_doc.changed.connect(self._on_photo)
        self._dz_doc.hide()
        row.addWidget(self._dz_doc, stretch=1)

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

        self._on_mode()          # hide the document-only controls to start with

    # ------------------------------------------------------------------
    def _document_mode(self) -> bool:
        return self._mode.currentData() == "document"

    def _on_mode(self) -> None:
        """Swap the screen between the 3×4 maker and the document scanner."""
        document = self._document_mode()
        self._dz.setVisible(not document)
        self._dz_doc.setVisible(document)
        self._bg_label.setVisible(not document)
        self._bg.setVisible(not document)
        self._grey.setVisible(document)
        self._reset.setVisible(document)
        self._copy.setEnabled(False)
        self._save.setEnabled(False)
        self._result_png = None
        self._result_pdf = None
        self._preview.setPixmap(QPixmap())
        self._preview.setText("Tayyor hujjat shu yerda ko'rinadi"
                              if document else "Tayyor rasm shu yerda ko'rinadi")
        self._status.setText(
            "Hujjat rasmlarini yuklang — chetlari topilib to'g'rilanadi, "
            "sahifa markaziga qo'yilib PDF bo'ladi. Bir nechta rasm "
            "yuklasangiz hammasi bitta PDF ga tushadi."
            if document else
            "Rasm yuklang — dastur 3×4 qilib, fonini tozalab beradi.")
        if (self._dz_doc.paths if document else self._dz.path):
            self._on_photo()

    def _on_photo(self) -> None:
        if self._document_mode():
            self._scan_documents()
            return
        if self._dz.path is None:
            return
        data = Path(self._dz.path).read_bytes()
        self._save.setEnabled(False)
        self._copy.setEnabled(False)
        self._status.setText("⏳ Rasm ishlanyapti…")
        self._progress.start("Rasm ishlanyapti…")
        run_async(self._service.process, data, bg=self._bg.currentData(),
                  on_success=self._done, on_error=self._failed)

    def _scan_documents(self) -> None:
        paths = self._dz_doc.paths
        if not paths:
            return
        from src.services import doc_scan_service

        images = [Path(p).read_bytes() for p in paths]
        grey = self._grey.isChecked()
        self._save.setEnabled(False)
        self._copy.setEnabled(False)
        self._status.setText(f"⏳ {len(images)} ta hujjat skanerlanyapti…")
        self._progress.start("Hujjat skanerlanyapti…")

        def work():
            return (doc_scan_service.build_pdf(images, grayscale=grey),
                    doc_scan_service.preview_png(images[0], grayscale=grey))

        run_async(work, on_success=self._scanned, on_error=self._failed)

    def _scanned(self, made: tuple[bytes, bytes]) -> None:
        pdf, preview = made
        self._progress.finish()
        self._result_pdf, self._result_png = pdf, preview
        self._show(preview)
        self._save.setEnabled(True)
        self._copy.setEnabled(True)
        count = len(self._dz_doc.paths)
        self._status.setText(
            f"✅ Tayyor: {count} ta hujjat → PDF. «Saqlash» bosing."
            + ("  (Ko'rinayotgani — birinchisi.)" if count > 1 else ""))

    def _show(self, png: bytes) -> None:
        pix = QPixmap.fromImage(QImage.fromData(png, "PNG")).scaled(
            self._preview.width(), self._preview.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._preview.setPixmap(pix)

    def _done(self, result: PhotoResult) -> None:
        self._progress.finish()
        self._result_png = result.png
        self._result_pdf = None
        self._show(result.png)
        self._save.setEnabled(True)
        self._copy.setEnabled(True)
        if result.face_found:
            extra = f"  [{result.note}]" if result.note else ""
            self._status.setText("✅ Tayyor: 3×4. Saqlang yoki Copy qiling." + extra)
        else:
            self._status.setText("⚠️ Yuz topilmadi — rasm faqat 3×4 qilib kesildi.")

    def _failed(self, error: Exception) -> None:
        self._progress.fail()
        self._status.setText("❌ " + str(error))
        QMessageBox.warning(self, "Xato", str(error))

    # ------------------------------------------------------------------
    def _save_photo(self) -> None:
        if self._result_pdf:
            path, _ = QFileDialog.getSaveFileName(
                self, "Hujjatni saqlash", "hujjat.pdf", "PDF (*.pdf)")
            if not path:
                return
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            Path(path).write_bytes(self._result_pdf)
            self._status.setText(f"✅ Saqlandi: {path}")
            return
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

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        """A new worker, or a new stack of documents — clear both piles."""
        self._dz.clear()
        self._dz_doc.clear()
        self._result_png = None
        self._result_pdf = None
        self._save.setEnabled(False)
        self._copy.setEnabled(False)
        self._preview.setPixmap(QPixmap())
        self._preview.setText("Tayyor hujjat shu yerda ko'rinadi"
                              if self._document_mode()
                              else "Tayyor rasm shu yerda ko'rinadi")
