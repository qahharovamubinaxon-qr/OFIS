"""РАСМ-ФОТО — odam rasmi (3×4) va hujjat skaneri.

Ikki rejim, bitta ekran:

* **Odam rasmi** — istalgan foto → yuz bo'yicha 3×4 (yoki 3.5×4.5…) kesiladi,
  foni olib tashlanadi (oq / kulrang / ko'k / studiya / shaffof), yuzi AI bilan
  tiklanadi, va 3×2 varaq PDF bo'ladi.
* **Hujjat** — pasport / patent / ID-karta surati → chetlari topilib
  perspektivadan to'g'rilanadi, skaner ko'rinishida A4 markaziga qo'yiladi.

Butun rasm ishlash mantiqi `photo_tools` yadrosida; bu ekran unga faqat
:class:`~src.services.photo_lab_service.PhotoLabService` orqali ulanadi va
og'ir ishni fon oqimida (`run_async`) bajaradi — oyna hech qachon qotmaydi.
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
    QProgressDialog,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from src.common.logging import get_logger
from src.common.threading import run_async
from src.services.photo_lab_service import (
    DocScanOutput,
    PersonPhotoOutput,
    PhotoLabService,
)
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)

_SIZES = (("3×4 см — 35×45", "35x45"), ("3×4 — 30×40", "30x40"),
          ("4×5 см — 40×50", "40x50"), ("5×5 см — 50×50", "50x50"))
_BACKGROUNDS = (("⬜ Оq", "white"), ("◽ Оch kulrang", "lightgray"),
                ("🟦 Ko'k", "blue"), ("🎬 Studiya", "studio"),
                ("▦ Shaffof (PNG)", "transparent"))
_GRIDS = (("6 ta — 3×2", "3x2"), ("4 ta — 2×2", "2x2"), ("8 ta — 4×2", "4x2"))
_PRESETS = (("ID-karta / patent", "id_card"), ("Pasport — 1 sahifa", "passport_page"),
            ("Pasport — ochiq, 2 sahifa", "passport_spread"),
            ("A4", "a4"), ("A5", "a5"), ("Avto", "auto"))
_COLORS = (("Rangli", "color"), ("Kulrang", "gray"), ("Oq-qora", "bw"))


class PhotoView(QWidget):
    def __init__(self, service: PhotoLabService, settings=None) -> None:
        super().__init__()
        self._service = service
        self._settings = settings
        self._out: PersonPhotoOutput | DocScanOutput | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("РАСМ-ФОТО — 3×4 расм ва ҳужжат сканери")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- mode ------------------------------------------------------
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Nima kerak:"))
        self._mode = QComboBox()
        self._mode.addItem("🧍 Odam rasmi — 3×4", "photo")
        self._mode.addItem("📄 Hujjat — skan → PDF", "document")
        self._mode.setFixedWidth(230)
        self._mode.currentIndexChanged.connect(self._on_mode)
        mode_row.addWidget(self._mode)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        # -- person settings ------------------------------------------
        self._person_opts = QWidget()
        po = QHBoxLayout(self._person_opts)
        po.setContentsMargins(0, 0, 0, 0)
        po.addWidget(QLabel("O'lcham:"))
        self._size = self._combo(_SIZES)
        po.addWidget(self._size)
        po.addWidget(QLabel("Fon:"))
        self._bg = self._combo(_BACKGROUNDS)
        po.addWidget(self._bg)
        self._enhance = QCheckBox("Yuzni AI bilan tiklash")
        self._enhance.setToolTip("Telefon suratidagi yuzni AI (GFPGAN) bilan "
                                 "tiniqlashtiradi. Model yo'q bo'lsa oddiy "
                                 "o'tkirlash bilan ishlaydi.")
        self._enhance.stateChanged.connect(self._on_enhance_toggle)
        po.addWidget(self._enhance)
        self._weight = QSlider(Qt.Orientation.Horizontal)
        self._weight.setRange(30, 100)
        self._weight.setValue(50)
        self._weight.setFixedWidth(90)
        self._weight.setToolTip("AI kuchi: 0.3–0.5 tabiiy (hujjat uchun), "
                                "1.0 — maksimal qayta chizish.")
        self._weight_lbl = QLabel("0.50")
        self._weight.valueChanged.connect(
            lambda v: self._weight_lbl.setText(f"{v / 100:.2f}"))
        po.addWidget(self._weight)
        po.addWidget(self._weight_lbl)
        self._corner = QCheckBox("Burchak kesimi")
        self._corner.setChecked(True)
        self._corner.setToolTip("Pastki chap burchak diagonal kesiladi "
                                "(obrazets kabi).")
        po.addWidget(self._corner)
        po.addWidget(QLabel("Varaq:"))
        self._grid = self._combo(_GRIDS)
        po.addWidget(self._grid)
        po.addStretch(1)
        root.addWidget(self._person_opts)

        # -- document settings ----------------------------------------
        self._doc_opts = QWidget()
        do = QHBoxLayout(self._doc_opts)
        do.setContentsMargins(0, 0, 0, 0)
        do.addWidget(QLabel("Hujjat turi:"))
        self._preset = self._combo(_PRESETS)
        do.addWidget(self._preset)
        do.addWidget(QLabel("Rang:"))
        self._color = self._combo(_COLORS)
        do.addWidget(self._color)
        do.addStretch(1)
        root.addWidget(self._doc_opts)

        # -- upload → preview -----------------------------------------
        row = QHBoxLayout()
        row.setSpacing(16)

        self._dz = DropZone("🖼️", "Rasm yuklang (istalgan foto)")
        self._dz.changed.connect(self._on_input)
        row.addWidget(self._dz, stretch=1)

        self._doc_box = QWidget()
        dbl = QHBoxLayout(self._doc_box)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(10)
        self._dz_front = DropZone("📄", "Old tomoni")
        self._dz_front.changed.connect(self._on_input)
        dbl.addWidget(self._dz_front, stretch=1)
        self._dz_back = DropZone("🔄", "Orqa tomoni (ixtiyoriy)")
        self._dz_back.changed.connect(self._on_input)
        dbl.addWidget(self._dz_back, stretch=1)
        row.addWidget(self._doc_box, stretch=2)

        arrow = QLabel("→")
        arrow.setStyleSheet("font-size: 28px; color:#8a94a3;")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(arrow)

        right = QVBoxLayout()
        self._preview = QLabel("Tayyor natija shu yerda ko'rinadi")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(260, 340)
        self._preview.setStyleSheet(
            "border: 2px dashed #3a4354; border-radius: 12px; color:#8a94a3;")
        right.addWidget(self._preview, stretch=1)

        btns = QHBoxLayout()
        self._save_pdf = QPushButton("💾 PDF")
        self._save_pdf.clicked.connect(self._on_save_pdf)
        self._save_png = QPushButton("🖼 PNG")
        self._save_png.clicked.connect(self._on_save_png)
        self._copy = QPushButton("📋 Copy")
        self._copy.clicked.connect(self._on_copy)
        for b in (self._save_pdf, self._save_png, self._copy):
            b.setEnabled(False)
            btns.addWidget(b)
        right.addLayout(btns)
        row.addLayout(right, stretch=2)
        root.addLayout(row, stretch=1)

        run_row = QHBoxLayout()
        self._run = QPushButton("▶ Tayyorlash")
        self._run.setObjectName("primaryButton")
        self._run.clicked.connect(self._on_run)
        run_row.addWidget(self._run)
        clear = QPushButton("🗑 Tozalash")
        clear.clicked.connect(self.reset)
        run_row.addWidget(clear)
        run_row.addStretch(1)
        root.addLayout(run_row)

        self._progress = RunProgress(self)
        root.addWidget(self._progress)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

        self._restore_choices()
        self._on_enhance_toggle()
        self._on_mode()

    # ------------------------------------------------------------- helpers
    def _combo(self, pairs) -> QComboBox:
        box = QComboBox()
        for label, key in pairs:
            box.addItem(label, key)
        return box

    def _document_mode(self) -> bool:
        return self._mode.currentData() == "document"

    def _grid_cols_rows(self) -> tuple[int, int]:
        cols, rows = (self._grid.currentData() or "3x2").split("x")
        return int(cols), int(rows)

    # ------------------------------------------------------------- settings
    def _restore_choices(self) -> None:
        if self._settings is None:
            return
        try:
            self._pick(self._mode, self._settings.get("photo.mode", "photo"))
            self._pick(self._size, self._settings.get("photo.size", "35x45"))
            self._pick(self._bg, self._settings.get("photo.bg", "white"))
            self._pick(self._grid, self._settings.get("photo.grid", "3x2"))
            self._pick(self._preset, self._settings.get("photo.preset", "id_card"))
            self._pick(self._color, self._settings.get("photo.color", "color"))
            self._enhance.setChecked(
                str(self._settings.get("photo.enhance", "1")) == "1")
            weight = str(self._settings.get("photo.weight", "50"))
            if weight.isdigit():
                self._weight.setValue(int(weight))
        except Exception:                          # noqa: BLE001 - never block UI
            log.debug("photo: settings restore skipped", exc_info=True)

    def _remember(self) -> None:
        if self._settings is None:
            return
        try:
            self._settings.set("photo.mode", self._mode.currentData())
            self._settings.set("photo.size", self._size.currentData())
            self._settings.set("photo.bg", self._bg.currentData())
            self._settings.set("photo.grid", self._grid.currentData())
            self._settings.set("photo.preset", self._preset.currentData())
            self._settings.set("photo.color", self._color.currentData())
            self._settings.set("photo.enhance",
                               "1" if self._enhance.isChecked() else "0")
            self._settings.set("photo.weight", str(self._weight.value()))
        except Exception:                          # noqa: BLE001
            log.debug("photo: settings save skipped", exc_info=True)

    @staticmethod
    def _pick(box: QComboBox, key) -> None:
        index = box.findData(key)
        if index >= 0:
            box.setCurrentIndex(index)

    # ------------------------------------------------------------- state
    def _on_enhance_toggle(self) -> None:
        on = self._enhance.isChecked()
        self._weight.setEnabled(on)
        self._weight_lbl.setEnabled(on)

    def _on_mode(self) -> None:
        document = self._document_mode()
        self._person_opts.setVisible(not document)
        self._doc_opts.setVisible(document)
        self._dz.setVisible(not document)
        self._doc_box.setVisible(document)
        self._clear_result()
        self._preview.setText("Tayyor hujjat shu yerda ko'rinadi" if document
                              else "Tayyor rasm shu yerda ko'rinadi")
        self._status.setText(
            "Old (va xohlasangiz orqa) tomonini yuklang — chetlari topilib "
            "to'g'rilanadi, A4 markaziga qo'yilib PDF bo'ladi." if document else
            "Rasm yuklang — 3×4 qilib kesadi, fonini tozalaydi, varaq qiladi.")

    def _on_input(self) -> None:
        # a fresh upload invalidates the last result; the operator presses
        # «Tayyorlash» when ready (heavy work never starts on a stray drop)
        self._clear_result()

    def _clear_result(self) -> None:
        self._out = None
        self._preview.setPixmap(QPixmap())
        for b in (self._save_pdf, self._save_png, self._copy):
            b.setEnabled(False)

    # ------------------------------------------------------------- run
    def _on_run(self) -> None:
        if self._document_mode():
            self._run_document()
        else:
            self._run_person()

    def _run_person(self) -> None:
        if self._dz.path is None:
            self._warn("Avval rasm yuklang.")
            return
        if self._enhance.isChecked() and not self._ensure_face_model():
            return                       # download offered/declined → handled
        data = Path(self._dz.path).read_bytes()
        cols, rows = self._grid_cols_rows()
        opts = dict(size=self._size.currentData(),
                    background=self._bg.currentData(),
                    enhance_face=self._enhance.isChecked(),
                    face_weight=self._weight.value() / 100,
                    corner_cut=self._corner.isChecked(), cols=cols, rows=rows)
        self._remember()
        self._busy("⏳ Rasm ishlanyapti…")
        run_async(self._service.person, data, on_success=self._person_done,
                  on_error=self._failed, **opts)

    def _run_document(self) -> None:
        if self._dz_front.path is None:
            self._warn("Avval hujjatning old tomonini yuklang.")
            return
        items = [(Path(self._dz_front.path).read_bytes(), "old")]
        if self._dz_back.path is not None:
            items.append((Path(self._dz_back.path).read_bytes(), "orqa"))
        opts = dict(preset=self._preset.currentData(),
                    color=self._color.currentData())
        self._remember()
        self._busy("⏳ Hujjat skanerlanyapti…")
        run_async(self._service.document, items, on_success=self._doc_done,
                  on_error=self._failed, **opts)

    def _busy(self, message: str) -> None:
        self._out = None
        self._run.setEnabled(False)
        for b in (self._save_pdf, self._save_png, self._copy):
            b.setEnabled(False)
        self._status.setText(message)
        self._progress.start(message)

    def _person_done(self, out: PersonPhotoOutput) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._out = out
        self._show(out.sheet_png)
        for b in (self._save_pdf, self._save_png, self._copy):
            b.setEnabled(True)
        if not out.face_found:
            self._status.setText("⚠️ Yuz topilmadi — rasm faqat markazdan "
                                 "kesildi. PDF: 6 ta rasm.")
        else:
            extra = " · AI bilan tiklandi" if out.face_enhanced else ""
            self._status.setText(f"✅ Tayyor{extra}. PDF — varaq, PNG — bitta "
                                 "rasm, Copy — buferga.")

    def _doc_done(self, out: DocScanOutput) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._out = out
        self._show(out.preview_png)
        for b in (self._save_pdf, self._save_png, self._copy):
            b.setEnabled(True)
        pages = len(out.page_pngs)
        self._status.setText(f"✅ Tayyor: {pages} sahifa → PDF. PNG — har "
                             "sahifa alohida.")

    def _failed(self, error: Exception) -> None:
        self._progress.fail()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")
        QMessageBox.warning(self, "Xato", message)

    def _show(self, png: bytes) -> None:
        pix = QPixmap.fromImage(QImage.fromData(png, "PNG")).scaled(
            self._preview.width(), self._preview.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._preview.setPixmap(pix)

    # ------------------------------------------------------------- models
    def _ensure_face_model(self) -> bool:
        """Ready to enhance? Offer the one-time model download if it is missing.

        Returns True when the run may proceed (model ready, or the operator
        chose to go on without AI). Returns False only while a download the
        operator asked for is running — the run restarts when it finishes.
        """
        status = self._service.models_status()
        if status.get("gfpgan"):
            return True
        if not status.get("torch"):
            QMessageBox.information(
                self, "AI yuz tiklash",
                "AI yuz tiklash uchun «torch» kutubxonasi kerak (dasturni u "
                "bilan qayta yig'ish lozim). Hozircha oddiy o'tkirlash bilan "
                "davom etadi.")
            return True                            # degrade gracefully, still run
        ask = QMessageBox.question(
            self, "Model yuklab olish",
            "AI yuz tiklash modeli (≈350 MB) hali yuklanmagan. Hozir yuklab "
            "olinsinmi? (Bir marta — keyin oflayn ishlaydi.)")
        if ask != QMessageBox.StandardButton.Yes:
            self._enhance.setChecked(False)        # go on without AI this time
            return True
        dialog = QProgressDialog("Model yuklab olinmoqda…", None, 0, 0, self)
        dialog.setWindowTitle("AI yuz tiklash")
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setCancelButton(None)
        dialog.show()

        def done(_status) -> None:
            dialog.close()
            self._run_person()                     # restart now that it is ready

        def failed(error: Exception) -> None:
            dialog.close()
            self._enhance.setChecked(False)
            self._warn(f"Model yuklanmadi: {error}. AI'siz davom etamiz — "
                       "«Tayyorlash» bosing.")

        run_async(self._service.ensure_models, on_success=done, on_error=failed)
        return False

    # ------------------------------------------------------------- save
    def _on_save_pdf(self) -> None:
        if self._out is None:
            return
        default = "hujjat.pdf" if self._document_mode() else "rasm_varaq.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "PDF saqlash", default, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        Path(path).write_bytes(self._out.pdf)
        self._status.setText(f"✅ Saqlandi: {path}")

    def _on_save_png(self) -> None:
        if self._out is None:
            return
        if isinstance(self._out, DocScanOutput):
            folder = QFileDialog.getExistingDirectory(self, "PNG'lar uchun papka")
            if not folder:
                return
            for i, png in enumerate(self._out.page_pngs, 1):
                (Path(folder) / f"hujjat_{i}.png").write_bytes(png)
            self._status.setText(
                f"✅ {len(self._out.page_pngs)} ta PNG saqlandi: {folder}")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Rasmni saqlash", "photo_3x4.png",
            "PNG (*.png);;JPEG (*.jpg)")
        if not path:
            return
        if path.lower().endswith((".jpg", ".jpeg")):
            QImage.fromData(self._out.photo_png, "PNG").save(path, "JPEG", 95)
        else:
            Path(path).write_bytes(self._out.photo_png)
        self._status.setText(f"✅ Saqlandi: {path}")

    def _on_copy(self) -> None:
        if self._out is None:
            return
        png = (self._out.preview_png if isinstance(self._out, DocScanOutput)
               else self._out.photo_png)
        QApplication.clipboard().setImage(QImage.fromData(png, "PNG"))
        self._status.setText("✅ Buferga nusxalandi (Ctrl+V bilan qo'ying).")

    # ------------------------------------------------------------- misc
    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        self._dz.clear()
        self._dz_front.clear()
        self._dz_back.clear()
        self._clear_result()
        self._status.setText("")
