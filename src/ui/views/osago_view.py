"""СТРАХОВКА МАШИНАГА — the ОСАГО policy from the car's own papers.

СТС front and back name the car and its owner; up to four licences name the
drivers. No licences uploaded → the policy covers anyone and the
«неограниченного количества лиц» box gets its mark; licences uploaded →
they go into the допущенные лица table and the other box is marked — both
exactly the way the insurer's own samples print them.
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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.osago_controller import OsagoController
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class OsagoView(QWidget):
    def __init__(self, controller: OsagoController) -> None:
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

        title = QLabel("СТРАХОВКА МАШИНАГА — ОСАГО полиси")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- blanks ----------------------------------------------------
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
        arrange.setToolTip("Матнларни суриш ва катта-кичик қилиш")
        arrange.clicked.connect(self._arrange)
        blank_row.addWidget(arrange)
        root.addLayout(blank_row)

        # -- the car's papers ------------------------------------------
        sts_row = QHBoxLayout()
        self._sts_front = DropZone("🚗", "СТС олди")
        sts_row.addWidget(self._sts_front)
        self._sts_back = DropZone("🚙", "СТС орқаси")
        sts_row.addWidget(self._sts_back)
        root.addLayout(sts_row)

        hint = QLabel("Права юкланмаса — «без ограничения»; юкланса (4 тагача) "
                      "— «лица, допущенные к управлению» рўйхатига тушади.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        lic_row = QHBoxLayout()
        self._licences: list[DropZone] = []
        for i in range(1, 5):
            zone = DropZone("🪪", f"Права {i}")
            self._licences.append(zone)
            lic_row.addWidget(zone)
        root.addLayout(lic_row)

        # -- inputs -----------------------------------------------------
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
        grid.addWidget(QLabel("Тугаши (ўзи 1 йил -1 кун):"), 0, 2)
        self._until = QLabel("")
        grid.addWidget(self._until, 0, 3)

        grid.addWidget(QLabel("Полис № (бланкада бўлса — бўш қолдиринг):"),
                       1, 0)
        self._policy_no = QLineEdit()
        grid.addWidget(self._policy_no, 1, 1)
        grid.addWidget(QLabel("Премия (ихтиёрий):"), 1, 2)
        self._premium = QLineEdit()
        grid.addWidget(self._premium, 1, 3)

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
        until = self._c.cover_until(self._from.date().toPython())
        self._until.setText(f"{until:%d.%m.%Y}")

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
        from src.pdf.osago_spec import BASE_TITLES

        source, _ = QFileDialog.getOpenFileName(
            self, "Полис бланкасини танланг (PDF)", "", "Бланка (*.pdf)")
        if not source:
            return
        name, ok = QInputDialog.getText(
            self, "Бланка номи", "Қайси компанияники? (ном беринг)")
        if not ok or not name.strip():
            return
        titles = list(BASE_TITLES.values())
        picked, ok = QInputDialog.getItem(
            self, "Услуб", "Бланка қайси услубда тўлдирилади?",
            titles, 0, False)
        if not ok:
            return
        base = [k for k, v in BASE_TITLES.items() if v == picked][0]
        try:
            dest = self._c.add_template(name.strip(), Path(source), base)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._template.setCurrentIndex(self._template.findData(str(dest)))
        self._status.setText(
            f"✅ «{dest.stem}» юкланди ({picked}). Матн жойларини «📐» билан "
            "текшириб олинг.")

    def _remove_template(self) -> None:
        template = self._template.currentData()
        if not template:
            return
        if QMessageBox.question(self, "Ўчириш", "Бланка ўчирилсинми?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_template(Path(template))
        self._reload()

    # ----------------------------------------------------------- arrange
    def _arrange(self) -> None:
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани танланг ёки юкланг.")
            return
        from datetime import date as _date

        import fitz

        from src.domain.vehicle import DriverLicence, Sts
        from src.pdf.osago_renderer import OsagoData, placed, values
        from src.pdf.osago_spec import BASES
        from src.ui.widgets.layout_editor import Item
        from src.ui.widgets.multipage_layout_editor import MultiPageLayoutEditor

        template = Path(template)
        base = self._c.base_of(template)
        try:
            with fitz.open(str(template)) as doc:
                pages = [doc[0].get_pixmap(dpi=110).tobytes("png")]
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        sample_data = OsagoData(
            sts=Sts(series="9981", number="585582", plate="М765НК193",
                    vin="XTA21150033523017", mark="VAZ", model="21150",
                    owner_fio="ДЕНИСОВА МАРИЯ СЕРГЕЕВНА"),
            drivers=[DriverLicence(surname="НАЙДЕНОВ", name="АЛЕКСЕЙ",
                                   patronymic="ВЛАДИМИРОВИЧ",
                                   series="9931", number="829630")],
            unlimited=False, start=_date(2026, 7, 15),
            until=_date(2027, 7, 14), policy_no="ТТТ 7075082339",
            premium="17241,56")
        sample = values(sample_data, base)
        slots = placed(self._c.layout(template), BASES[base])
        items = [Item(key=key, label=key, sample=sample.get(key) or key,
                      x=slot.x, baseline=slot.baseline, size=slot.size,
                      font_family="Calibri")
                 for key, slot in slots.items()]
        dialog = MultiPageLayoutEditor(pages, {1: items},
                                       title="СТРАХОВКА", parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.save_layout(template, {"fields": dialog.result().items})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText("✅ Матн жойлари сақланди.")

    # ---------------------------------------------------------- printing
    def _generate(self) -> None:
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани юкланг.")
            return
        if self._sts_front.path is None:
            self._warn("СТС олд томонининг расмини ташланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return

        sts_front = Path(self._sts_front.path).read_bytes()
        sts_back = (Path(self._sts_back.path).read_bytes()
                    if self._sts_back.path is not None else None)
        licences = [Path(z.path).read_bytes()
                    for z in self._licences if z.path is not None]
        start = self._from.date().toPython()
        policy_no = self._policy_no.text().strip()
        premium = self._premium.text().strip()

        self._run.setEnabled(False)
        self._progress.start("Ҳужжатлар ўқилиб, полис тўлдирилаяпти…")

        def work():
            return self._c.generate_from_images(
                template=Path(template), sts_front=sts_front,
                sts_back=sts_back, licences=licences, start=start,
                policy_no=policy_no, premium=premium)

        run_async(work, on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        who = ("без ограничения" if result.drivers == 0
               else f"{result.drivers} та ҳайдовчи")
        self._status.setText(f"✅ Тайёр: {result.saved} ({who})")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "osago"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
