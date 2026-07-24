"""Process Employee screen — the main workflow.

Top: company + form date + должность (apply to both modes).
Two paths: AI (upload passport+patent → RUN) and Manual (open the 16-field
table). Generation runs on a worker thread; the view only shows the result.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
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
from src.controllers.process_controller import ProcessController
from src.services.generation_service import GenerationResult
from src.services.manual_entry import DEFAULT_PROFESSION
from src.ui.i18n import Translator
from src.ui.views.manual_dialog import ManualFillDialog

log = get_logger(__name__)


class ProcessView(QWidget):
    def __init__(self, controller: ProcessController, translator: Translator) -> None:
        super().__init__()
        self._c = controller
        self._tr = translator
        self._passport_path: Path | None = None
        self._patent_path: Path | None = None
        self._patent_back_path: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel(self._tr.tr("nav.process", "Process Employee"))
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- company + date + должность --------------------------------
        row = QHBoxLayout()
        self._company = QComboBox()
        self._reload_companies()
        row.addWidget(QLabel("Фирма:"))
        row.addWidget(self._company, stretch=2)

        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(QLabel("Дата:"))
        row.addWidget(self._date)

        self._profession = QLineEdit(DEFAULT_PROFESSION)
        row.addWidget(QLabel("Должность:"))
        row.addWidget(self._profession, stretch=1)
        root.addLayout(row)

        # -- AI upload --------------------------------------------------
        up = QHBoxLayout()
        self._passport_btn = QPushButton("📷 Паспорт")
        self._passport_btn.clicked.connect(self._pick_passport)
        self._patent_btn = QPushButton("📷 Патент (олд)")
        self._patent_btn.clicked.connect(self._pick_patent)
        self._patent_back_btn = QPushButton("📷 Патент (орқа)")
        self._patent_back_btn.clicked.connect(self._pick_patent_back)
        up.addWidget(self._passport_btn)
        up.addWidget(self._patent_btn)
        up.addWidget(self._patent_back_btn)
        up.addStretch(1)
        root.addLayout(up)

        # -- actions ----------------------------------------------------
        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (AI)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._run_ai)
        self._manual = QPushButton("✎  Qo'lda to'ldirish")
        self._manual.clicked.connect(self._run_manual)
        self._batch = QPushButton("📦  ZIP (ko'p ishchi)")
        self._batch.clicked.connect(self._run_batch)
        actions.addWidget(self._run)
        actions.addWidget(self._manual)
        actions.addWidget(self._batch)
        actions.addStretch(1)
        root.addLayout(actions)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel(self._ai_hint())
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Called when the screen is shown — pick up new companies + reg number."""
        current = self._company.currentText()
        self._reload_companies()
        idx = self._company.findText(current)
        if idx >= 0:
            self._company.setCurrentIndex(idx)
        self._status.setText(self._ai_hint())

    def _reload_companies(self) -> None:
        self._company.clear()
        self._companies = self._c.companies()
        for comp in self._companies:
            self._company.addItem(comp.name)

    def _selected_company(self):
        idx = self._company.currentIndex()
        return self._companies[idx] if 0 <= idx < len(self._companies) else None

    def _form_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    def _ai_hint(self) -> str:
        if self._c.ai_available():
            return f"AI tayyor. Keyingi PDF raqami: {self._c.next_reg_number()}."
        return ("AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting yoki "
                f"«Qo'lda to'ldirish» dan foydalaning. Keyingi raqam: {self._c.next_reg_number()}.")

    def _pick_passport(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Паспорт", "", "Images (*.jpg *.jpeg *.png *.webp)")
        if path:
            self._passport_path = Path(path)
            self._passport_btn.setText(f"✓ Паспорт: {Path(path).name}")

    def _pick_patent(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Патент (олд томон)", "", "Images (*.jpg *.jpeg *.png *.webp)")
        if path:
            self._patent_path = Path(path)
            self._patent_btn.setText(f"✓ Патент олд: {Path(path).name}")

    def _pick_patent_back(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Патент (орқа томон)", "", "Images (*.jpg *.jpeg *.png *.webp)")
        if path:
            self._patent_back_path = Path(path)
            self._patent_back_btn.setText(f"✓ Патент орқа: {Path(path).name}")

    # ------------------------------------------------------------------
    def _run_ai(self) -> None:
        company = self._selected_company()
        if company is None:
            self._warn("Avval firma tanlang.")
            return
        if not self._c.ai_available():
            self._warn("AI kaliti yo'q. «Qo'lda to'ldirish» dan foydalaning yoki Sozlamalarga kalit kiriting.")
            return
        if self._passport_path is None:
            self._warn("Pasport rasmini yuklang.")
            return

        passport = self._c.read_image(self._passport_path)
        patent = self._c.read_image(self._patent_path) if self._patent_path else None
        patent_back = self._c.read_image(self._patent_back_path) if self._patent_back_path else None
        profession = self._profession.text().strip() or None
        form_date = self._form_date()
        self._busy("AI o'qiyapti va PDF yaratyapti…")
        run_async(
            self._c.generate_from_images, company, passport, patent, patent_back,
            form_date=form_date, profession=profession,
            on_success=self._done, on_error=self._failed,
        )

    def _run_manual(self) -> None:
        company = self._selected_company()
        if company is None:
            self._warn("Avval firma tanlang.")
            return
        dialog = ManualFillDialog(self._tr.language, prefill={"profession": self._profession.text().strip()}, parent=self)
        if dialog.exec() != ManualFillDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        profession = values.get("profession") or None
        form_date = self._form_date()
        self._busy("PDF yaratyapti…")
        run_async(
            self._c.generate_from_manual, company, values,
            form_date=form_date, profession=profession,
            on_success=self._done, on_error=self._failed,
        )

    def _run_batch(self) -> None:
        company = self._selected_company()
        if company is None:
            self._warn("Avval firma tanlang.")
            return
        if not self._c.ai_available():
            self._warn("ZIP paket rejimi AI bilan ishlaydi. Sozlamalarga Gemini kalitini kiriting.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Ishchilar ZIP fayli", "", "ZIP (*.zip)")
        if not path:
            return
        profession = self._profession.text().strip() or None
        form_date = self._form_date()
        self._busy("ZIP ochilyapti, har bir ishchi uchun PDF yaratyapti… (biroz kutiladi)")
        run_async(
            self._c.process_zip, Path(path), company,
            form_date=form_date, profession=profession,
            on_success=self._batch_done, on_error=self._failed,
        )

    def _batch_done(self, summary) -> None:
        self._enable()
        self._status.setText(f"✅ Paket tayyor: {summary.ok_count}/{summary.total}  →  {summary.output_dir}")
        failed = [i for i in summary.items if not i.ok]
        detail = ""
        if failed:
            detail = "\n\nBajarilmadi:\n" + "\n".join(f"• {i.folder}: {i.error}" for i in failed[:12])
        box = QMessageBox(self)
        box.setWindowTitle("Paket tayyor")
        box.setText(f"{summary.ok_count}/{summary.total} ta PDF yaratildi.\n{summary.output_dir}{detail}")
        open_btn = box.addButton("Papkani ochish", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_folder(summary.output_dir)

    # ------------------------------------------------------------------
    def _enable(self) -> None:
        self._run.setEnabled(True)
        self._manual.setEnabled(True)
        self._batch.setEnabled(True)

    def _busy(self, msg: str) -> None:
        self._run.setEnabled(False)
        self._manual.setEnabled(False)
        self._batch.setEnabled(False)
        self._status.setText("⏳ " + msg)

    def _done(self, result: GenerationResult) -> None:
        self._enable()
        self._status.setText(f"✅ Tayyor: {result.pdf_path.name}  (№ {result.reg_number})")
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"PDF yaratildi:\n{result.pdf_path}")
        open_btn = box.addButton("Papkani ochish", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_folder(result.pdf_path.parent)

    def _failed(self, error: Exception) -> None:
        self._enable()
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
