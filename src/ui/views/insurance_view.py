"""СТРАХОВКА МАШИНАГА — ОСАГО for the workers who drive the firm's cars.

Pick the insurer's template, drop in the photographs and set the day cover
starts — the end date follows by itself, one year to the day before.

Who the policy covers is not a question the operator answers: it follows from
what they uploaded. The СТС alone means «неограниченного количества лиц»; add
one to four driving licences and the policy names those drivers instead. Asking
for the answer as well only made it possible to say one thing and upload
another, which is what used to stop RUN before it started.
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
    QGridLayout,
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
from src.controllers.insurance_controller import InsuranceController
from src.services.insurance_service import MAX_DRIVERS, InsuranceResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)


class AddInsuranceTemplateDialog(QDialog):
    """Register another insurer's Word policy — the same way Трудовой does."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yangi страховка шаблони")
        self.setMinimumWidth(520)
        self.source: Path | None = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("СК «Согласие»")
        self.code = QLineEdit()
        self.code.setPlaceholderText("soglasie")
        self.insurer = QLineEdit()
        self.insurer.setPlaceholderText("СК «Согласие» — тўлиқ номи")
        self.firm = QLineEdit()
        self.firm.setPlaceholderText("Агентлик шартномаси қайси фирмамизда")
        form.addRow("Nomi *", self.name)
        form.addRow("Kod (unikal) *", self.code)
        form.addRow("Страховая компания", self.insurer)
        form.addRow("Bizning firma", self.firm)
        outer.addLayout(form)

        self._label = QLabel("Шаблон tanlanmagan (Word .docx)")
        pick = QPushButton("Шаблон (.docx)…")
        pick.clicked.connect(self._pick)
        row = QHBoxLayout()
        row.addWidget(self._label, stretch=1)
        row.addWidget(pick)
        outer.addLayout(row)

        hint = QLabel("Тўлдирилган полисни юкласангиз ҳам бўлади — программа "
                      "ичидаги эски машина ва ҳайдовчиларни ўчириб, янгисини ёзади.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a94a3;")
        outer.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Полис шаблони", "", "Word (*.docx)")
        if path:
            self.source = Path(path)
            self._label.setText(f"✓ {Path(path).name}")


class InsuranceView(QWidget):
    def __init__(self, controller: InsuranceController) -> None:
        super().__init__()
        self._c = controller
        self._templates: list = []

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("СТРАХОВКА МАШИНАГА — ОСАГО")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        self._template = QComboBox()
        row.addWidget(QLabel("Шаблон:"))
        row.addWidget(self._template, stretch=2)
        add = QPushButton("+ Yangi shablon")
        add.clicked.connect(self._add_template)
        row.addWidget(add)
        rm = QPushButton("🗑")
        rm.setFixedWidth(40)
        rm.setToolTip("Танланган шаблонни рўйхатдан олиш")
        rm.clicked.connect(self._remove_template)
        row.addWidget(rm)
        root.addLayout(row)

        dates = QHBoxLayout()
        self._start = QDateEdit()
        self._start.setDisplayFormat("dd.MM.yyyy")
        self._start.setDate(QDate.currentDate())
        self._start.setCalendarPopup(True)
        self._start.dateChanged.connect(self._retitle_end)
        dates.addWidget(QLabel("Бошланиши:"))
        dates.addWidget(self._start)
        self._end = QLabel()
        self._end.setObjectName("dzTitle")
        dates.addWidget(QLabel("Тугаши:"))
        dates.addWidget(self._end)
        dates.addStretch(1)
        dates.addWidget(QLabel("Страхователь:"))
        self._holder = QLineEdit()
        self._holder.setPlaceholderText("бўш қолса — СТСдаги эгаси")
        self._holder.setMinimumWidth(220)
        dates.addWidget(self._holder)
        root.addLayout(dates)

        # «Договор заключен в отношении» is not a question the operator has to
        # answer: it follows from what they uploaded. No licences means the
        # policy covers anyone; one to four means it names them.
        choice = QFrame()
        choice_box = QVBoxLayout(choice)
        choice_box.setContentsMargins(0, 0, 0, 0)
        choice_box.addWidget(QLabel("Договор заключен в отношении:"))
        self._coverage = QLabel()
        self._coverage.setWordWrap(True)
        choice_box.addWidget(self._coverage)
        root.addWidget(choice)

        grid = QGridLayout()
        grid.setSpacing(12)
        self._sts_front = DropZone("🚗", "СТС (олд)")
        self._sts_back = DropZone("🔄", "СТС (орқа)")
        grid.addWidget(self._sts_front, 0, 0)
        grid.addWidget(self._sts_back, 0, 1)
        self._licences = [DropZone("🪪", f"Права {i + 1}")
                          for i in range(MAX_DRIVERS)]
        for i, zone in enumerate(self._licences):
            grid.addWidget(zone, 1 + i // 2, i % 2)
            zone.changed.connect(self._coverage_changed)
        root.addLayout(grid)

        self._run = QPushButton("RUN — полисни тўлдириш")
        self._run.setObjectName("primaryButton")
        self._run.clicked.connect(self._start_run)
        root.addWidget(self._run)

        self._progress = RunProgress()
        root.addWidget(self._progress)
        self._status = QLabel()
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)

        self.refresh()
        self._retitle_end()
        self._coverage_changed()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        try:
            self._templates = self._c.templates()
        except OfisError as exc:
            self._templates = []
            self._status.setText("⚠️ " + exc.message)
        self._template.clear()
        for template in self._templates:
            label = template.name
            if template.insurer and template.insurer != template.name:
                label = f"{template.name} — {template.insurer}"
            self._template.addItem(label)
        self._status.setText(self._hint())

    def _hint(self) -> str:
        if not self._templates:
            return "Шаблон йўқ — «+ Yangi shablon» орқали Word полисни юкланг."
        if self._c.ai_available():
            return ("СТС олд/орқа юкланг — фақат шуниси бўлса полис "
                    "«без ограничения» бўлади. Права ҳам юкласангиз (1—4 та) "
                    "«лиц, допущенных к управлению» белгиланади. "
                    "Полис серия/номерини страховая компания беради.")
        return "AI калити йўқ — Созламаларга AI калитини киритинг."

    def _selected(self):
        idx = self._template.currentIndex()
        return self._templates[idx] if 0 <= idx < len(self._templates) else None

    def _start_date(self) -> date:
        q = self._start.date()
        return date(q.year(), q.month(), q.day())

    def _retitle_end(self) -> None:
        """One year of cover, ending the day before the anniversary."""
        end = self._c.cover_until(self._start_date())
        self._end.setText(end.strftime("%d.%m.%Y"))

    def _uploaded_licences(self) -> list:
        return [z.path for z in self._licences if z.path is not None]

    def _coverage_changed(self) -> None:
        """Say which line will be ticked, and why, before RUN is pressed."""
        count = len(self._uploaded_licences())
        if count:
            self._coverage.setText(
                f"✅ лиц, допущенных к управлению транспортным средством "
                f"— {count} та права юкланди")
        else:
            self._coverage.setText(
                "✅ неограниченного количества лиц, допущенных к управлению "
                "транспортным средством — права юкланмади")

    # ------------------------------------------------------------ templates
    def _add_template(self) -> None:
        dialog = AddInsuranceTemplateDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.source is None:
            QMessageBox.warning(self, "Diqqat", "Word шаблон файлини танланг.")
            return
        try:
            self._c.add_template(dialog.name.text(), dialog.code.text(),
                                 dialog.source, insurer=dialog.insurer.text(),
                                 firm=dialog.firm.text())
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        self.refresh()
        self._template.setCurrentIndex(self._template.count() - 1)

    def _remove_template(self) -> None:
        template = self._selected()
        if template is None:
            return
        if QMessageBox.question(
                self, "O'chirish",
                f"«{template.name}» рўйхатдан олинсинми?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._c.archive_template(template.id)
        self.refresh()

    # ---------------------------------------------------------------- the run
    def _start_run(self) -> None:
        template = self._selected()
        if template is None:
            self._warn("Аввал шаблон танланг.")
            return
        if self._sts_front.path is None:
            self._warn("СТС нинг олд томонини юкланг.")
            return
        licences = self._uploaded_licences()
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Созламаларга Gemini калитини киритинг.")
            return

        self._run.setEnabled(False)
        self._progress.start("Расмлар ўқиляпти…")
        run_async(
            self._c.generate_from_images, template,
            self._c.read_image(self._sts_front.path),
            self._c.read_image(self._sts_back.path) if self._sts_back.path else None,
            [self._c.read_image(p) for p in licences],
            start=self._start_date(),          # the upload decides the coverage
            policy_holder=self._holder.text(),
            on_success=self._done, on_error=self._failed)

    def _done(self, result: InsuranceResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        lines = [f"✅ {result.plate or 'Полис'} тайёр — {result.drivers} та ҳайдовчи.",
                 f"📄 {result.docx_path.name}"]
        if result.pdf_path is not None:
            lines.append(f"📄 {result.pdf_path.name}")
        lines += [f"ℹ️ {note}" for note in result.notes]
        self._status.setText("\n".join(lines))

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("⚠️ " + message)
        QMessageBox.warning(self, "Xato", message)

    def _warn(self, message: str) -> None:
        self._status.setText("⚠️ " + message)
