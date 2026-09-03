"""3-СПРАВКА — the six-page certificate from two photographs and two inputs.

Passport in one slot; the second slot takes whatever prints the worker's ФИО
in Russian — the patent or the миграционная карта. The operator picks the
start date (the end is always a year minus a day, shown, never typed) and
types the address; the packet comes out as one PDF named after the worker.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.spr3_controller import Spr3Controller
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class Spr3View(QWidget):
    def __init__(self, controller: Spr3Controller) -> None:
        super().__init__()
        self._c = controller

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

        title = QLabel("3-СПРАВКА — 6 варақли гувоҳнома")
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
        arrange.setToolTip("6 саҳифада матнларни суриб жойлаштириш")
        arrange.clicked.connect(self._arrange)
        blank_row.addWidget(arrange)
        root.addLayout(blank_row)

        # -- the two photographs ---------------------------------------
        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        self._passport.changed.connect(self._on_dropped)
        docs.addWidget(self._passport)
        self._name_doc = DropZone("🪪", "Русча ФИО ҳужжати (патент/миг карта)")
        self._name_doc.changed.connect(self._on_dropped)
        docs.addWidget(self._name_doc)
        root.addLayout(docs)

        # what was read, for the operator to check before printing
        from src.ui.widgets.passport_review import PassportReview
        self._review = PassportReview()
        root.addWidget(self._review)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(400)
        self._settle.timeout.connect(self._read_now)

        # -- the inputs -------------------------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)

        grid.addWidget(QLabel("Бошланиш санаси:"), 0, 0)
        self._from = QDateEdit(QDate.currentDate())
        self._from.setCalendarPopup(True)
        self._from.setDisplayFormat("dd.MM.yyyy")
        self._from.dateChanged.connect(self._show_until)
        grid.addWidget(self._from, 0, 1)
        grid.addWidget(QLabel("Тугаши (ўзи ҳисобланади):"), 0, 2)
        self._until = QLabel("")
        grid.addWidget(self._until, 0, 3)

        grid.addWidget(QLabel("3-саҳифа № (иккита рақам):"), 1, 0)
        self._num3 = QLineEdit()
        self._num3.setPlaceholderText("масалан 450215 6510668")
        grid.addWidget(self._num3, 1, 1)
        grid.addWidget(QLabel("3-саҳифа серия:"), 1, 2)
        self._ser3 = QLineEdit()
        self._ser3.setPlaceholderText("масалан 235035")
        grid.addWidget(self._ser3, 1, 3)
        grid.addWidget(QLabel("5-саҳифа №:"), 2, 0)
        self._num5 = QLineEdit()
        self._num5.setPlaceholderText("масалан 45Г 8889529")
        grid.addWidget(self._num5, 2, 1)

        # the address goes onto page 5 in the form's own pieces
        grid.addWidget(QLabel("Область:"), 3, 0)
        self._oblast = QLineEdit()
        grid.addWidget(self._oblast, 3, 1)
        grid.addWidget(QLabel("Город:"), 3, 2)
        self._gorod = QLineEdit()
        grid.addWidget(self._gorod, 3, 3)
        grid.addWidget(QLabel("Улица:"), 4, 0)
        self._ulitsa = QLineEdit()
        grid.addWidget(self._ulitsa, 4, 1)
        grid.addWidget(QLabel("Дом:"), 4, 2)
        self._dom = QLineEdit()
        grid.addWidget(self._dom, 4, 3)
        grid.addWidget(QLabel("Корпус:"), 5, 0)
        self._korpus = QLineEdit()
        grid.addWidget(self._korpus, 5, 1)
        grid.addWidget(QLabel("Квартира:"), 5, 2)
        self._kvartira = QLineEdit()
        grid.addWidget(self._kvartira, 5, 3)

        # -- run --------------------------------------------------------
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
        self._show_until()

    # ------------------------------------------------------------- state
    def _show_until(self) -> None:
        until = self._c.until(self._from.date().toPython())
        self._until.setText(f"{until:%d.%m.%Y}" if until else "")

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

    # ------------------------------------------------------------ blanks
    def _add_template(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "6 саҳифали бланкани танланг", "", "Бланка (*.pdf)")
        if not source:
            return
        name, ok = QInputDialog.getText(
            self, "Бланка номи", "Бу бланка қайси фирманики?")
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
            f"✅ «{dest.stem}» юкланди. «📐 Матнларни жойлаш» билан 6 та "
            "саҳифани бирма-бир тўғрилаб чиқинг.")

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
        """All six pages in one dialog — 2 and 4 stay blank and are skipped."""
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани танланг ёки юкланг.")
            return
        import fitz

        from src.pdf.spr3_renderer import Spr3Data, placed, values
        from src.ui.widgets.layout_editor import Item
        from src.ui.widgets.multipage_layout_editor import MultiPageLayoutEditor

        template = Path(template)
        try:
            pages = []
            with fitz.open(str(template)) as doc:
                for page in doc:
                    pages.append(page.get_pixmap(dpi=100).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        from datetime import date

        sample = values(Spr3Data(
            surname="ТУРДУБЕК", name="УУЛУ", patronymic="АЙТУРГАН",
            citizenship="КИРГИЗИЯ", birth_date=date(1998, 7, 9),
            gender="female", pass_series="ID", pass_number="1294780",
            pass_issued=date(2019, 7, 8), pass_issued_by="ГРС 212011",
            valid_from=date(2026, 6, 16),
            num3="450215 6510668", ser3="235035", num5="45Г 8889529",
            oblast="Московская область", gorod="г Химки",
            ulitsa="пр-кт Рязанский", dom="72", korpus="2", kvartira="134"))
        slots = placed(self._c.layout(template))
        items_by_page: dict[int, list[Item]] = {}
        for key, slot in slots.items():
            if slot.page > len(pages):
                continue
            items_by_page.setdefault(slot.page, []).append(
                Item(key=key, label=key, sample=sample.get(key) or key,
                     x=slot.x, baseline=slot.baseline, size=slot.size,
                     font_family="Times New Roman"))

        dialog = MultiPageLayoutEditor(pages, items_by_page,
                                       title="3-СПРАВКА", parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.save_layout(template, {"fields": dialog.result().items})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(
            f"✅ «{template.stem}» бланкасининг матн жойлари сақланди.")

    # ------------------------------------------------------------ printing
    # ------------------------------------------------------------ reading
    def _on_dropped(self) -> None:
        """Passport landed — read after a settle (with the ФИО document if
        present, for the Russian name)."""
        if self._passport.path is None or not self._c.ai_available():
            return
        self._settle.start()

    def _read_now(self) -> None:
        if self._passport.path is None or not self._c.ai_available():
            return
        passport = self._c.read_image(self._passport.path)
        name_doc = (self._c.read_image(self._name_doc.path)
                    if self._name_doc.path is not None else None)
        self._status.setText("⏳ Ҳужжатлар ўқиляпти…")
        self._progress.start("Ҳужжатлар ўқиляпти…")
        run_async(self._c.read_documents, passport, name_doc,
                  on_success=self._filled, on_error=self._read_failed)

    def _filled(self, passport) -> None:
        self._progress.finish()
        self._review.fill(passport)
        self._status.setText("✅ Ўқилди — текширинг, хатоси бўлса тўғриланг, "
                             "кейин Тайёрлаш.")

    def _read_failed(self, error: Exception) -> None:
        self._progress.finish()
        self._review.reveal()          # so it can be typed by hand
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ Ўқилмади: {message}. Қўлда ёзинг.")

    # ------------------------------------------------------------ printing
    def _generate(self) -> None:
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани юкланг.")
            return
        if self._review.isHidden():
            self._warn("Паспорт расмини ташланг — ўқилсин.")
            return
        if not self._review.has_surname():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return
        when = self._from.date().toPython()
        address = {"oblast": self._oblast.text(), "gorod": self._gorod.text(),
                   "ulitsa": self._ulitsa.text(), "dom": self._dom.text(),
                   "korpus": self._korpus.text(),
                   "kvartira": self._kvartira.text()}
        num3, ser3, num5 = (self._num3.text().strip(),
                            self._ser3.text().strip(),
                            self._num5.text().strip())

        self._run.setEnabled(False)
        self._progress.start("6 варақ тўлдирилаяпти…")
        run_async(
            self._c.generate, template=Path(template),
            passport=self._review.edited(),
            valid_from=when, address=address,
            num3=num3, ser3=ser3, num5=num5,
            on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._passport.clear()
        self._name_doc.clear()
        self._review.reset()
        self._status.setText(f"✅ Тайёр: {result.saved}")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "spr3"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
