"""МВД ТРУДАВОЙ — the ten-page packet, from three photographs and two picks.

The operator drops the passport and the patent's two sides, picks the date and
the должность, presses «Тайёрлаш» — and the whole packet comes out as one PDF
named after the worker. The blank is the firm's own ten-page scan; a new one
is uploaded once and its texts dragged into place page by page.
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
from src.controllers.mvd_trud_controller import MvdTrudController
from src.pdf.mvd_trud_spec import PROFESSIONS
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class MvdTrudView(QWidget):
    def __init__(self, controller: MvdTrudController) -> None:
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

        title = QLabel("МВД ТРУДАВОЙ — 10 варақли тўплам")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- region + blank --------------------------------------------
        blank_row = QHBoxLayout()
        blank_row.addWidget(QLabel("Қисм:"))
        self._region = QComboBox()
        from src.pdf.mvd_trud_spec import REGION_TITLES, REGIONS

        for region in REGIONS:
            self._region.addItem(REGION_TITLES[region], region)
        self._region.currentIndexChanged.connect(lambda _i: self._reload())
        blank_row.addWidget(self._region)
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
        arrange.setToolTip("Ҳамма саҳифада матнларни суриб жойлаштириш")
        arrange.clicked.connect(self._arrange)
        blank_row.addWidget(arrange)
        root.addLayout(blank_row)

        # -- the three photographs -------------------------------------
        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        self._passport.changed.connect(self._on_dropped)
        docs.addWidget(self._passport)
        self._front = DropZone("🩷", "Патент олди")
        self._front.changed.connect(self._on_dropped)
        docs.addWidget(self._front)
        self._back = DropZone("🩶", "Патент орқаси")
        self._back.changed.connect(self._on_dropped)
        docs.addWidget(self._back)
        root.addLayout(docs)

        # what was read, for the operator to check before printing
        from src.ui.widgets.passport_review import PassportReview
        self._review = PassportReview()
        root.addWidget(self._review)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(400)
        self._settle.timeout.connect(self._read_now)
        self._reading = False        # a read is in flight (AI is slow the 1st time)

        # -- the picks --------------------------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)

        grid.addWidget(QLabel("Сана (число):"), 0, 0)
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._date, 0, 1)

        grid.addWidget(QLabel("Должность:"), 0, 2)
        self._profession = QComboBox()
        self._profession.setEditable(True)
        self._profession.addItems(PROFESSIONS)
        grid.addWidget(self._profession, 0, 3)

        grid.addWidget(QLabel("Уведомление № (ихтиёрий):"), 1, 0)
        self._uved_no = QLineEdit()
        grid.addWidget(self._uved_no, 1, 1)
        grid.addWidget(QLabel("Справка № (ихтиёрий):"), 1, 2)
        self._spravka_no = QLineEdit()
        grid.addWidget(self._spravka_no, 1, 3)

        grid.addWidget(QLabel("Иш жойи адреси (область, эсда қолади):"), 2, 0)
        self._work_address = QLineEdit(self._c.work_address())
        self._work_address.setPlaceholderText(
            "масалан Московская обл., г. Подольск, ул. Большая "
            "Серпуховская, д. 43с12")
        grid.addWidget(self._work_address, 2, 1, 1, 3)

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

    # ------------------------------------------------------------- state
    def _picked_region(self) -> str:
        return self._region.currentData() or "moscow"

    def _reload(self) -> None:
        current = self._template.currentData()
        self._template.clear()
        for blank in self._c.templates(self._picked_region()):
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
            self, "10 саҳифали бланкани танланг", "", "Бланка (*.pdf)")
        if not source:
            return
        name, ok = QInputDialog.getText(
            self, "Бланка номи", "Бу бланка қайси фирманики? (масалан ГЛОБАЛПРО)")
        if not ok or not name.strip():
            return
        try:
            dest = self._c.add_template(name.strip(), Path(source),
                                        self._picked_region())
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._template.setCurrentIndex(self._template.findData(str(dest)))
        self._status.setText(
            f"✅ «{dest.stem}» юкланди. «📐 Матнларни жойлаш» билан ҳар "
            "саҳифадаги матнларни текшириб чиқинг.")

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
        """Every page's values, dragged into place inside ONE dialog."""
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани танланг ёки юкланг.")
            return
        import fitz

        from src.pdf.mvd_trud_renderer import placed, values_for
        from src.pdf.mvd_trud_spec import SLOTS_BY_REGION
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


        region = self._picked_region()
        sample = values_for(_sample_data(), region)
        slots = placed(self._c.layout(template), SLOTS_BY_REGION[region])
        items_by_page: dict[int, list[Item]] = {}
        for key, slot in slots.items():
            if slot.page > len(pages):
                continue
            shown = sample.get(key) or key
            if slot.pitch > 0:
                # cells read better spaced — and the sample must show the
                # WHOLE first row, or a long value looks cut short when it is
                # really wrapping onto the form's continuation row below
                room = slot.per_row or 14
                shown = " ".join(shown[:min(room, 30)])
            items_by_page.setdefault(slot.page, []).append(
                Item(key=key, label=key, sample=shown, x=slot.x,
                     baseline=slot.baseline, size=slot.size,
                     font_family="Times New Roman"))

        dialog = MultiPageLayoutEditor(pages, items_by_page,
                                       title="МВД ТРУДАВОЙ", parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.save_layout(template, {"fields": dialog.result().items})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(
            f"✅ «{template.stem}» бланкасининг матн жойлари сақланди — "
            "ҳамма саҳифада.")

    # ------------------------------------------------------------ reading
    def _on_dropped(self) -> None:
        """Passport + patent front both landed — read them after a settle.

        The ТРУД packet needs the patent's own number and dates printed, so it
        reads only once both the passport and the patent front are in."""
        if (self._passport.path is None or self._front.path is None
                or not self._c.ai_available()):
            return
        self._settle.start()

    def _read_now(self) -> None:
        if self._passport.path is None or self._front.path is None:
            return
        passport = self._c.read_image(self._passport.path)
        front = self._c.read_image(self._front.path)
        back = (self._c.read_image(self._back.path)
                if self._back.path is not None else None)
        self._reading = True
        self._status.setText("⏳ AI ҳужжатларни ўқияпти…")
        self._progress.start("Ҳужжатлар ўқиляпти…")
        run_async(self._c.read_documents, passport, front, back,
                  on_success=self._filled, on_error=self._read_failed)

    def _filled(self, pair) -> None:
        self._reading = False
        self._progress.finish()
        passport, patent = pair
        self._review.fill(passport, patent)
        self._status.setText("✅ Ўқилди — текширинг, хатоси бўлса тўғриланг, "
                             "кейин Тайёрлаш.")

    def _read_failed(self, error: Exception) -> None:
        self._reading = False
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
            # the operator pressed Тайёрлаш before the read finished (the first
            # read of a session is slow while the free tiers are probed). Say
            # so, and START the read if it has not begun — nothing is lost.
            if self._reading:
                self._warn("AI ҳужжатларни ўқияпти — бир оз кутинг, тайёр "
                           "бўлгач текшириб, яна Тайёрлаш босинг.")
                return
            if not self._c.ai_available():
                self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
                return
            if self._passport.path is not None and self._front.path is not None:
                self._read_now()
                self._warn("AI ўқий бошлади — тайёр бўлгач майдонларни "
                           "текшириб, яна Тайёрлаш босинг.")
                return
            self._warn("Паспорт ва патент олди расмини ташланг.")
            return
        if not self._review.has_surname():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return
        when = self._date.date().toPython()
        profession = self._profession.currentText().strip()
        uved_no = self._uved_no.text().strip()
        spravka_no = self._spravka_no.text().strip()
        work_address = self._work_address.text().strip()
        if work_address:
            self._c.remember_work_address(work_address)

        self._run.setEnabled(False)
        self._progress.start("10 варақ тўлдирилаяпти…")
        run_async(
            self._c.generate,
            template=Path(template), passport=self._review.edited(),
            patent=self._review.edited_patent(), profession=profession,
            deal_date=when, uved_no=uved_no, spravka_no=spravka_no,
            work_address=work_address,
            on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._passport.clear()
        self._front.clear()
        self._back.clear()
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

        folder = paths.output_dir() / "mvd_trud"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass


def _sample_data():
    """What the arrange screen shows in each slot — a believable worker."""
    from datetime import date

    from src.pdf.mvd_trud_renderer import MvdTrudData, plus_one_year

    return MvdTrudData(
        surname="ИВАНОВ", name="ИВАН", patronymic="ИВАНОВИЧ",
        citizenship="ТАДЖИКИСТАН", birth_date=date(1985, 12, 14),
        pass_number="402090755", pass_issued=date(2018, 5, 15),
        pass_issued_by="МВД", pat_series="77", pat_number="2600184371",
        pat_issued=date(2026, 4, 15),
        pat_issued_by="ОТДЕЛ ВНЕШНЕЙ ТРУДОВОЙ МИГРАЦИИ УВМ ГУ МВД",
        profession="ПОДСОБНЫЙ РАБОЧИЙ", deal_date=date(2026, 7, 28),
        pat_until=plus_one_year(date(2026, 4, 15)),
        uved_no="1259", spravka_no="160")
