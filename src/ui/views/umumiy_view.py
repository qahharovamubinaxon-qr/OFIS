"""УМУМИЙ screen — reuse any office document for a new worker.

Two ways to work:

* **Saved template** — add a document once («➕ Шаблон қўшиш»): the program
  studies it, blanks the previous worker's details and remembers where each
  value goes. Afterwards pick the template from the list, drop the new worker's
  documents and RUN — no AI, instant, always the same layout.
* **One-off** — drop a document straight into the left box, as before.

Scanned PDFs work in both modes: with no text layer the pages are read as
images instead of failing with «matn topilmadi».
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.threading import run_async
from src.ocr.service import OcrService
from src.services.umumiy_service import UmumiyResult, UmumiyService
from src.services.umumiy_templates import UmumiyTemplateService
from src.ui.widgets.multi_drop import PDF_EXTS, MultiDropZone
from src.ui.widgets.run_progress import RunProgress


class UmumiyView(QWidget):
    def __init__(self, ocr: OcrService, service: UmumiyService,
                 templates: UmumiyTemplateService | None = None) -> None:
        super().__init__()
        self._ocr = ocr
        self._svc = service
        self._templates = templates
        self._items: list = []

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("УМУМИЙ — ҳужжатни янги ишчига мослаш")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- saved templates --------------------------------------------
        if self._templates is not None:
            tpl_row = QHBoxLayout()
            tpl_row.addWidget(QLabel("Шаблон:"))
            self._tpl = QComboBox()
            self._tpl.setMinimumWidth(320)
            self._tpl.currentIndexChanged.connect(self._on_template_changed)
            tpl_row.addWidget(self._tpl)
            add = QPushButton("➕ Шаблон қўшиш")
            add.setToolTip("Ҳужжатни юкланг — ишчи маълумотлари ўчирилиб, "
                           "жойлари эсда сақланади")
            add.clicked.connect(self._add_template)
            tpl_row.addWidget(add)
            self._del = QPushButton("🗑")
            self._del.setFixedWidth(40)
            self._del.setToolTip("Танланган шаблонни ўчириш")
            self._del.clicked.connect(self._remove_template)
            tpl_row.addWidget(self._del)
            tpl_row.addStretch(1)
            root.addLayout(tpl_row)

        # -- date --------------------------------------------------------
        row = QHBoxLayout()
        row.addWidget(QLabel("Ҳужжат санаси:"))
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(self._date)
        row.addStretch(1)
        root.addLayout(row)

        # -- two drop areas side by side ---------------------------------
        up = QHBoxLayout()
        up.setSpacing(14)
        self._dz_doc = MultiDropZone(
            "Ҳужжат (PDF) — қайта ишланадиган", limit=1,
            exts=PDF_EXTS, icon="📄", min_height=170)
        self._dz_worker = MultiDropZone(
            "Ишчи ҳужжатлари — паспорт · патент · миграционка (хоҳлаганча)",
            limit=10, icon="🛂", min_height=170)
        # dropping the worker's documents reads them straight away
        self._dz_worker.changed.connect(self._on_dropped)
        up.addWidget(self._dz_doc, stretch=1)
        up.addWidget(self._dz_worker, stretch=1)
        root.addLayout(up, stretch=1)

        # what was read, for the operator to check before printing
        from src.ui.widgets.passport_review import PassportReview
        self._review = PassportReview()
        root.addWidget(self._review)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(400)
        self._settle.timeout.connect(self._read_now)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (Умумий)")
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

        self._status = QLabel(
            "Шаблон танланг ёки чап томонга ҳужжат (PDF) юкланг. Скан PDF ҳам "
            "бўлаверади. Фирма реквизитлари (ИНН, ОГРН, директор) "
            "ўзгартирилмайди — фақат ишчи маълумотлари."
        )
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

        self.refresh()

    # -- templates -----------------------------------------------------
    def refresh(self) -> None:
        if self._templates is None:
            return
        self._items = self._templates.list()
        self._tpl.blockSignals(True)
        self._tpl.clear()
        self._tpl.addItem("— шаблонсиз (ҳужжатни ўзим юкламан) —", None)
        for tpl in self._items:
            self._tpl.addItem(tpl.label, tpl.slug)
        self._tpl.blockSignals(False)
        self._on_template_changed()

    def _selected_slug(self) -> str | None:
        if self._templates is None:
            return None
        return self._tpl.currentData()

    def _on_template_changed(self) -> None:
        using = self._selected_slug() is not None
        self._dz_doc.setEnabled(not using)
        self._del.setEnabled(using)
        self._status.setText(
            "Шаблон танланди — фақат ишчи ҳужжатларини юкланг."
            if using else
            "Шаблон танланг ёки чап томонга ҳужжат (PDF) юкланг. Скан PDF ҳам "
            "бўлаверади."
        )

    def _add_template(self) -> None:
        if not self._ocr.available():
            self._warn("AI калити йўқ — Sozlamalarга Gemini калитини киритинг.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Шаблон учун ҳужжат танланг", "", "PDF (*.pdf)")
        if not path:
            return
        name, ok = QInputDialog.getText(
            self, "Шаблон номи", "Бу ҳужжатни нима деб сақлайлик?",
            text=Path(path).stem)
        if not ok or not name.strip():
            return

        self._run.setEnabled(False)
        self._status.setText("⏳ Шаблон ўрганилаяпти — ишчи маълумотлари "
                             "топилиб, жойлари эсда сақланяпти…")
        self._progress.start("Шаблон тайёрланяпти…")
        run_async(self._templates.create, Path(path), name.strip(),
                  on_success=self._template_added, on_error=self._failed)

    def _template_added(self, tpl) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        self.refresh()
        idx = self._tpl.findData(tpl.slug)
        if idx >= 0:
            self._tpl.setCurrentIndex(idx)
        self._status.setText(
            f"✅ «{tpl.name}» сақланди — {tpl.fields} та майдон топилди."
            + (" (скан ҳужжат)" if tpl.scanned else ""))

    def _remove_template(self) -> None:
        slug = self._selected_slug()
        if slug is None:
            return
        name = self._tpl.currentText()
        if QMessageBox.question(self, "Ўчириш",
                                f"«{name}» ўчирилсинми?") != QMessageBox.StandardButton.Yes:
            return
        self._templates.delete(slug)
        self.refresh()

    # ------------------------------------------------------------------
    def _form_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    # ------------------------------------------------------------ reading
    def _on_dropped(self) -> None:
        """The worker's documents landed — read them after a short settle."""
        if not self._dz_worker.files or not self._ocr.available():
            return
        self._settle.start()

    def _read_now(self) -> None:
        if not self._dz_worker.files or not self._ocr.available():
            return
        images = [f.read_bytes() for f in self._dz_worker.files]
        self._review.start_reading()
        self._status.setText("⏳ Ҳужжатлар ўқиляпти…")
        self._progress.start("Ҳужжатлар ўқиляпти…")

        def work():
            # Any mix of worker documents is accepted: the first image is read
            # as the identity document, the rest add patent/migration details.
            return self._ocr.read_documents(
                images[0],
                images[1] if len(images) > 1 else None,
                images[2] if len(images) > 2 else None,
            )

        run_async(work, on_success=self._filled, on_error=self._read_failed)

    def _filled(self, pair) -> None:
        self._progress.finish()
        passport, patent = pair
        self._review.fill(passport, patent)
        self._status.setText("✅ Ўқилди — текширинг, хатоси бўлса тўғриланг, "
                             "кейин RUN.")

    def _read_failed(self, error: Exception) -> None:
        self._progress.finish()
        self._review.reveal()          # so it can be typed by hand
        msg = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ Ўқилмади: {msg}. Қўлда ёзинг.")

    # ------------------------------------------------------------ printing
    def _run_ai(self) -> None:
        slug = self._selected_slug()
        if slug is None and not self._dz_doc.files:
            self._warn("Шаблон танланг ёки қайта ишланадиган ҳужжатни (PDF) юкланг.")
            return
        from src.ui.widgets.passport_review import ready_or_start
        if not ready_or_start(
                self._review, has_images=bool(self._dz_worker.files),
                ai_available=self._ocr.available(), start_read=self._read_now,
                warn=self._warn,
                no_images_msg="Ишчининг камида битта ҳужжат расмини юкланг."):
            return
        if not self._review.has_surname():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return

        source = self._dz_doc.files[0] if self._dz_doc.files else None
        form_date = self._form_date()
        templates = self._templates
        passport = self._review.edited()
        patent = self._review.edited_patent()

        def work():
            if slug is not None:
                path = templates.fill(slug, passport, patent, form_date=form_date)
                tpl = templates.get(slug)
                return UmumiyResult(pdf_path=path,
                                    replacements=tpl.fields if tpl else 0,
                                    surname=passport.surname)
            return self._svc.generate(source, passport, patent, form_date=form_date)

        self._run.setEnabled(False)
        self._status.setText(
            "⏳ Шаблон тўлдирилаяпти…" if slug is not None
            else "⏳ Янги ишчига мосланяпти…")
        self._progress.start("Ҳужжат тайёрланяпти…")
        run_async(work, on_success=self._done, on_error=self._failed)

    # ------------------------------------------------------------------
    def _done(self, result: UmumiyResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        self._dz_worker.clear_files()
        self._review.reset()
        from src.ui.widgets.save_to import ask_save_dir

        saved = ask_save_dir(self, [result.pdf_path])
        extra = f" → {saved}" if saved else ""
        self._status.setText(
            f"✅ Тайёр: {result.pdf_path.name}  ·  {result.replacements} та "
            f"маълумот алмаштирилди{extra}")
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"Ҳужжат тайёр:\n{result.pdf_path}\n\n"
                    f"Алмаштирилган маълумотлар: {result.replacements} та\n"
                    "Илтимос, чоп этишдан олдин текшириб чиқинг.")
        open_btn = box.addButton("Papkani ochish", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            _open_folder(result.pdf_path.parent)

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        msg = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + msg)
        self._warn(msg)

    def _warn(self, msg: str) -> None:
        QMessageBox.warning(self, "Diqqat", msg)


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
