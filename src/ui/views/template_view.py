"""ЎЗ ШАБЛОНИМ — upload any form and let the program work it out.

Upload a PDF or a Word file, press «Таҳлил» and the program shows what it found:
one row per place it thinks a value goes. Nothing is used until the operator has
been through that list — a row can be re-pointed at a different field or removed
outright. What is confirmed is remembered against the file's contents, so the
same document is never studied twice.

Then the worker's passport and patent go in, and the form is filled and checked.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.common.threading import run_async
from src.controllers.template_controller import TemplateController
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)

_COLUMNS = ("Нима ёзилади", "Ҳужжатдаги ёрлиқ", "Жойи", "")


class TemplateView(QWidget):
    def __init__(self, controller: TemplateController) -> None:
        super().__init__()
        self._c = controller
        self._template: Path | None = None
        self._study = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ЎЗ ШАБЛОНИМ — программа ўзи тушунади")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        self._file = QLabel("Шаблон танланмаган (PDF ёки Word)")
        pick = QPushButton("Шаблон танлаш…")
        pick.clicked.connect(self._pick)
        self._analyse = QPushButton("Таҳлил қилиш")
        self._analyse.setObjectName("primaryButton")
        self._analyse.clicked.connect(self._study_template)
        self._analyse.setEnabled(False)
        row.addWidget(self._file, stretch=1)
        row.addWidget(pick)
        row.addWidget(self._analyse)
        root.addLayout(row)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        root.addWidget(self._table, stretch=1)

        confirm_row = QHBoxLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("Шаблон номи (рўйхатда кўринади)")
        self._save = QPushButton("Тасдиқлаш ва эслаб қолиш")
        self._save.clicked.connect(self._remember)
        self._save.setEnabled(False)
        confirm_row.addWidget(QLabel("Номи:"))
        confirm_row.addWidget(self._name, stretch=1)
        confirm_row.addWidget(self._save)
        root.addLayout(confirm_row)

        fill_row = QHBoxLayout()
        self._dz_passport = DropZone("🛂", "Паспорт")
        self._dz_patent = DropZone("📄", "Патент")
        fill_row.addWidget(self._dz_passport)
        fill_row.addWidget(self._dz_patent)
        root.addLayout(fill_row)

        run_row = QHBoxLayout()
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._profession = QLineEdit()
        self._profession.setPlaceholderText("Профессия (ихтиёрий)")
        self._run = QPushButton("RUN — шаблонни тўлдириш")
        self._run.setObjectName("primaryButton")
        self._run.clicked.connect(self._fill)
        run_row.addWidget(QLabel("Сана:"))
        run_row.addWidget(self._date)
        run_row.addWidget(self._profession, stretch=1)
        run_row.addWidget(self._run)
        root.addLayout(run_row)

        self._progress = RunProgress()
        root.addWidget(self._progress)
        self._status = QLabel("Шаблон юкланг — программа ичидаги майдонларни "
                              "ўзи топади, сиз фақат тасдиқлайсиз.")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

    # ------------------------------------------------------------------
    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Шаблон", "", "PDF/Word (*.pdf *.docx)")
        if not path:
            return
        self._template = Path(path)
        self._file.setText(f"✓ {self._template.name}")
        self._analyse.setEnabled(True)
        self._name.setText(self._template.stem)

    def _study_template(self) -> None:
        if self._template is None:
            return
        self._analyse.setEnabled(False)
        self._progress.start("Шаблон ўрганиляпти…")
        run_async(self._c.study, self._template,
                  on_success=self._studied, on_error=self._failed)

    def _studied(self, outcome) -> None:
        study, remembered = outcome
        self._analyse.setEnabled(True)
        self._progress.finish()
        self._study = study
        self._show(study)
        self._save.setEnabled(bool(study.spots))
        if remembered:
            self._status.setText(
                f"ℹ️ Бу шаблон аввал ўрганилган — {len(study.spots)} та жой "
                "тайёр. Керак бўлса ўзгартиринг.")
        elif study.spots:
            self._status.setText(
                f"✅ {len(study.spots)} та жой топилди ({study.kind}). "
                "Кўриб чиқинг: нотўғрисини ўчиринг ёки бошқа майдонга буринг, "
                "сўнг «Тасдиқлаш».")
        else:
            self._status.setText("⚠️ " + "; ".join(study.notes))

    def _show(self, study) -> None:
        fields = self._c.fields()
        self._table.setRowCount(len(study.spots))
        for row, spot in enumerate(study.spots):
            picker = QComboBox()
            for key, label in fields:
                picker.addItem(label, key)
            picker.setCurrentIndex(
                next((i for i, (k, _l) in enumerate(fields) if k == spot.key), 0))
            picker.currentIndexChanged.connect(
                lambda _i, r=row, p=picker: self._repoint(r, p))
            self._table.setCellWidget(row, 0, picker)

            for column, text in ((1, spot.label), (2, spot.describe())):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self._table.setItem(row, column, item)

            drop = QPushButton("Ўчириш")
            drop.clicked.connect(lambda _c=False, r=row: self._drop(r))
            self._table.setCellWidget(row, 3, drop)

    def _repoint(self, row: int, picker: QComboBox) -> None:
        """The operator says this place is really a different field."""
        if self._study is None or row >= len(self._study.spots):
            return
        spot = self._study.spots[row]
        spot.key = picker.currentData()
        spot.confirmed = True

    def _drop(self, row: int) -> None:
        """A place the program found that is not a place at all."""
        if self._study is None or row >= len(self._study.spots):
            return
        del self._study.spots[row]
        self._show(self._study)
        self._save.setEnabled(bool(self._study.spots))

    def _remember(self) -> None:
        if self._study is None or self._template is None:
            return
        for spot in self._study.spots:
            spot.confirmed = True
        try:
            self._template = self._c.remember(self._name.text().strip(),
                                              self._template, self._study)
        except OfisError as exc:
            QMessageBox.warning(self, "Хато", exc.message)
            return
        self._status.setText(
            f"✅ Эслаб қолинди — {len(self._study.spots)} та жой. Бу шаблон "
            "кейинги сафар қайта таҳлил қилинмайди.")

    # ------------------------------------------------------------------
    def _fill(self) -> None:
        if self._study is None or self._template is None:
            self._status.setText("⚠️ Аввал шаблонни таҳлил қилинг.")
            return
        if self._dz_passport.path is None:
            self._status.setText("⚠️ Паспорт расмини юкланг.")
            return
        if not self._c.ai_available():
            self._status.setText("⚠️ AI калити йўқ — Созламаларга киритинг.")
            return

        out = self._template.with_name(
            f"{self._template.stem}_TOLDIRILGAN{self._template.suffix}")
        q = self._date.date()
        self._run.setEnabled(False)
        self._progress.start("Ҳужжатлар ўқиляпти…")
        run_async(self._c.fill_from_images, self._study, self._template, out,
                  self._c.read_image(self._dz_passport.path),
                  self._c.read_image(self._dz_patent.path)
                  if self._dz_patent.path else None,
                  form_date=date(q.year(), q.month(), q.day()),
                  profession=self._profession.text().strip(),
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, result) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        from src.ui.widgets.save_to import ask_save_dir

        saved_to = ask_save_dir(self, [result.path])
        lines = [f"✅ Тайёр: {result.path.name} — {len(result.written)} та қиймат.",
                 f"📁 Сақланди: {saved_to}" if saved_to
                 else f"📁 Программа папкасида: {result.path.parent}"]
        lines += [f"⚠️ {problem}" for problem in result.problems]
        self._status.setText("\n".join(lines))
        QMessageBox.information(self, "Тайёр", "\n".join(lines[:2]))

    def _failed(self, error: Exception) -> None:
        self._analyse.setEnabled(True)
        self._run.setEnabled(True)
        self._progress.fail()
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + message)
