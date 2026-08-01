"""РУС РЕГ — registration sheets for the office's Russian-citizen workers.

The operator drops ONE document — a Russian internal passport for a grown
worker, or a birth certificate for a worker's child — and the sheet's «вид»
line follows whichever it was. Everything typed once (the address, the firm,
the running number) is still in the fields tomorrow; the button beside the
address opens every address the office has ever registered at.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.rusreg_controller import RusRegController
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class RusRegView(QWidget):
    def __init__(self, controller: RusRegController) -> None:
        super().__init__()
        self._c = controller
        #: which document the fields were last filled from — it is what the
        #: sheet's «вид» line prints, so it follows the upload, not a guess
        self._is_passport = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(12)

        title = QLabel("РУС РЕГ — ишчини регистрацияси")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- blank -----------------------------------------------------
        blank_row = QHBoxLayout()
        blank_row.addWidget(QLabel("Бланка:"))
        self._template = QComboBox()
        blank_row.addWidget(self._template, stretch=1)
        add_blank = QPushButton("➕ Бланка")
        add_blank.clicked.connect(self._add_template)
        blank_row.addWidget(add_blank)
        drop_blank = QPushButton("🗑")
        drop_blank.setToolTip("Танланган бланкани ўчириш")
        drop_blank.clicked.connect(self._remove_template)
        blank_row.addWidget(drop_blank)
        arrange = QPushButton("📐 Матнларни жойлаш")
        arrange.setToolTip("Бланкада матнларни сичқонча билан суриб жойлаштириш")
        arrange.clicked.connect(self._arrange)
        blank_row.addWidget(arrange)
        root.addLayout(blank_row)

        # -- the two documents ----------------------------------------
        docs = QHBoxLayout()
        self._passport_zone = DropZone("🛂", "Паспорт РФ")
        self._passport_zone.changed.connect(lambda: self._on_document(True))
        docs.addWidget(self._passport_zone)
        self._birth_zone = DropZone("👶", "Метрка (свидетельство о рождении)")
        self._birth_zone.changed.connect(lambda: self._on_document(False))
        docs.addWidget(self._birth_zone)
        root.addLayout(docs)

        # -- fields ----------------------------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)

        self._reg_number = self._line(grid, 0, 0, "Регистрация №:")
        self._firm = self._line(grid, 0, 2, "Фирма (ОТДЕЛ КАДРОВ …):")

        self._surname = self._line(grid, 1, 0, "Фамилия:")
        self._name = self._line(grid, 1, 2, "Исм:")
        self._patronymic = self._line(grid, 2, 0, "Отчество:")
        self._birth = self._line(grid, 2, 2, "Туғилган сана (КК.ОО.ЙЙЙЙ):")
        # the birth place is a sentence, not a word — it gets the whole row
        grid.addWidget(QLabel("Туғилган жойи:"), 3, 0)
        self._birth_place = QLineEdit()
        grid.addWidget(self._birth_place, 3, 1, 1, 3)

        grid.addWidget(QLabel("Адрес:"), 4, 0)
        addr_row = QHBoxLayout()
        self._address = QLineEdit()
        addr_row.addWidget(self._address, stretch=1)
        history = QPushButton("📋")
        history.setToolTip("Олдин ишлатилган адреслар")
        history.clicked.connect(self._show_addresses)
        addr_row.addWidget(history)
        grid.addLayout(addr_row, 4, 1, 1, 3)

        self._series = self._line(grid, 5, 0, "Ҳужжат серияси:")
        self._number = self._line(grid, 5, 2, "Ҳужжат №:")
        self._issued = self._line(grid, 6, 0, "Берилган сана (КК.ОО.ЙЙЙЙ):")
        self._issued_by = self._line(grid, 6, 2, "Берган орган:")
        self._signer = self._line(grid, 7, 0, "Имзо (фамилия):")

        grid.addWidget(QLabel("Срок: бошланиши"), 8, 0)
        self._from = self._date_edit(QDate.currentDate())
        grid.addWidget(self._from, 8, 1)
        grid.addWidget(QLabel("тугаши"), 8, 2)
        self._to = self._date_edit(QDate.currentDate().addMonths(3))
        grid.addWidget(self._to, 8, 3)

        # -- run -------------------------------------------------------
        run_row = QHBoxLayout()
        self._run = QPushButton("🖨 Тайёрлаш")
        self._run.setObjectName("primaryButton")
        self._run.clicked.connect(self._generate)
        run_row.addWidget(self._run)
        open_out = QPushButton("📂 Папкани очиш")
        open_out.clicked.connect(self._open_folder)
        run_row.addWidget(open_out)
        run_row.addStretch(1)
        root.addLayout(run_row)

        self._progress = RunProgress(self)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)

        self._reload()
        self._restore()

    # ------------------------------------------------------------ widgets
    @staticmethod
    def _date_edit(when: QDate) -> QDateEdit:
        edit = QDateEdit(when)
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd.MM.yyyy")
        return edit

    def _line(self, grid: QGridLayout, row: int, col: int, label: str) -> QLineEdit:
        grid.addWidget(QLabel(label), row, col)
        edit = QLineEdit()
        grid.addWidget(edit, row, col + 1)
        return edit

    # ------------------------------------------------------------- state
    def _reload(self) -> None:
        current = self._template.currentData()
        self._template.clear()
        for blank in self._c.templates():
            self._template.addItem(blank.stem, str(blank))
        if self._template.count() == 0:
            self._template.addItem("— бланка юкланмаган —", None)
        elif current:
            index = self._template.findData(current)
            if index >= 0:
                self._template.setCurrentIndex(index)

    def _restore(self) -> None:
        """What the office typed last time is already in the fields."""
        kept = self._c.remembered()
        self._address.setText(kept["address"])
        self._firm.setText(kept["firm"])
        self._reg_number.setText(kept["reg_number"])
        self._signer.setText(kept["signer"])

    def _show_addresses(self) -> None:
        known = self._c.addresses()
        if not known:
            self._warn("Ҳали адрес йўқ — биринчисини ёзинг, ўзи сақланади.")
            return
        menu = QMenu(self)
        for address in known:
            menu.addAction(address, lambda a=address: self._address.setText(a))
        menu.exec(self.mapToGlobal(self._address.geometry().bottomLeft()))

    # ------------------------------------------------------------ blanks
    def _add_template(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "Бланкани танланг", "",
            "Бланка (*.pdf *.png *.jpg *.jpeg)")
        if not source:
            return
        name, ok = QInputDialog.getText(
            self, "Бланка номи", "Бу бланка қайси фирманики? (масалан СФЕРА)")
        if not ok or not name.strip():
            return
        try:
            dest = self._c.add_template(name.strip(), Path(source))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._template.setCurrentIndex(self._template.findData(str(dest)))
        self._status.setText(
            f"✅ «{dest.stem}» бланкаси юкланди. Энди «📐 Матнларни жойлаш» "
            "билан матнларни ўз жойига қўйиб чиқинг.")

    def _remove_template(self) -> None:
        template = self._template.currentData()
        if not template:
            return
        name = Path(template).stem
        if QMessageBox.question(
                self, "Ўчириш", f"«{name}» бланкаси ўчирилсинми?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_template(Path(template))
        self._reload()
        self._status.setText(f"«{name}» ўчирилди.")

    def _arrange(self) -> None:
        """Drag every value into place on THIS blank and keep it."""
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани танланг ёки юкланг.")
            return
        import fitz

        from src.pdf.rusreg_renderer import placed
        from src.pdf.rusreg_spec import FONT
        from src.ui.widgets.layout_editor import Item, LayoutEditor

        template = Path(template)
        try:
            with fitz.open(str(template)) as raw:
                doc = raw if raw.is_pdf else fitz.open("pdf", raw.convert_to_pdf())
                png = doc[0].get_pixmap(dpi=110).tobytes("png")
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        samples = {
            "reg_number": "1998/19/126",
            "fio_born": "ИВАНОВ ИВАН ИВАНОВИЧ, 30.05.1980  ГОДА РОЖДЕНИЯ",
            "birth_place": "Г. МОСКВА",
            "address_1": "Г. МОСКВА, УЛ. РЕМИЗОВА, Д. 4, КВ. 16",
            "address_2": "(адрес давоми)",
            "from_day": "31", "from_month": "ИЮЛЯ", "from_year": "2026",
            "to_day": "30", "to_month": "ИЮЛЯ", "to_year": "2027",
            "doc_kind": "ПАСПОРТ РФ", "doc_series": "45 25",
            "doc_number": "105235",
            "issued_day": "04", "issued_month": "ИЮНЯ", "issued_year": "2025",
            "issued_by": "ГУ МВД РОССИИ ПО Г. МОСКВЕ",
            "firm": "ОТДЕЛ КАДРОВ ООО СФЕРА",
            "signer": "ПРОКОПЕНКО А.Г.",
            "made_day": "31", "made_month": "ИЮЛЯ", "made_year": "2026",
        }
        spots = placed(self._c.layout(template))
        items = [Item(key=key, label=key, sample=samples.get(key, key),
                      x=x, baseline=baseline, size=size,
                      font_family="Times New Roman" if "Serif" in FONT
                      else FONT)
                 for key, (x, baseline, size) in spots.items()]
        dialog = LayoutEditor(png, items, title="РУС РЕГ — матнларни жойлаш",
                              parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.save_layout(template, {"fields": dialog.result().items})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(
            f"✅ «{template.stem}» бланкасининг матн жойлари сақланди.")

    # ---------------------------------------------------------- documents
    def _on_document(self, is_passport: bool) -> None:
        zone = self._passport_zone if is_passport else self._birth_zone
        if zone.path is None:
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        # one sheet names one document; the other zone empties so what is on
        # screen is exactly what will be printed
        (self._birth_zone if is_passport else self._passport_zone).clear()
        self._is_passport = is_passport
        data = Path(zone.path).read_bytes()
        kind = "Паспорт" if is_passport else "Метрка"
        self._status.setText(f"⏳ {kind} ўқилаяпти…")
        self._progress.start(f"{kind}дан маълумот олинаяпти…")
        run_async(self._c.read_document, data, is_passport=is_passport,
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, fields: dict[str, str]) -> None:
        self._progress.finish()
        for edit, key in ((self._surname, "surname"), (self._name, "name"),
                          (self._patronymic, "patronymic"),
                          (self._birth, "birth_date"),
                          (self._birth_place, "birth_place"),
                          (self._series, "series"), (self._number, "number"),
                          (self._issued, "issue_date"),
                          (self._issued_by, "issued_by")):
            if fields.get(key):
                edit.setText(fields[key])
        kind = "паспорт" if self._is_passport else "метрка"
        self._status.setText(
            f"✅ Ҳужжат ({kind}) ўқилди — текшириб, «Тайёрлаш»ни босинг.")

    # ------------------------------------------------------------ printing
    def _generate(self) -> None:
        template = self._template.currentData()
        q_from, q_to = self._from.date(), self._to.date()
        self._run.setEnabled(False)
        self._progress.start("РУС РЕГ тайёрланаяпти…")
        run_async(
            self._c.generate,
            template=Path(template) if template else None,
            reg_number=self._reg_number.text().strip(),
            surname=self._surname.text().strip(),
            name=self._name.text().strip(),
            patronymic=self._patronymic.text().strip(),
            birth_date=self._c.parse_date(self._birth.text()),
            birth_place=self._birth_place.text().strip(),
            address=self._address.text().strip(),
            valid_from=q_from.toPython(), valid_to=q_to.toPython(),
            is_passport=self._is_passport,
            doc_series=self._series.text().strip(),
            doc_number=self._number.text().strip(),
            doc_issued=self._c.parse_date(self._issued.text()),
            doc_issued_by=self._issued_by.text().strip(),
            firm=self._firm.text().strip(),
            signer=self._signer.text().strip(),
            on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._status.setText(f"✅ Тайёр: {result.saved}")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "rusreg"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
