"""КРКОД РЕГ — dormitory registration with the QR that proves it.

Passport + patent in, dates and the dormitory picked, one press: the
подтверждение card is filled, photographed to imgbb, its direct link becomes
the QR on the registration's back, and the two-page PDF lands on the Desktop
named after the worker.
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
from src.controllers.qrreg_controller import QrRegController
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class QrRegView(QWidget):
    def __init__(self, controller: QrRegController) -> None:
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

        title = QLabel("КРКОД РЕГ — QR кодли регистрация (йотоқхона)")
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
        drop_blank.clicked.connect(self._remove_template)
        blank_row.addWidget(drop_blank)
        arrange = QPushButton("📐 Матнларни жойлаш")
        arrange.clicked.connect(self._arrange_reg)
        blank_row.addWidget(arrange)
        root.addLayout(blank_row)

        podt_row = QHBoxLayout()
        self._podt_state = QLabel("")
        podt_row.addWidget(self._podt_state, stretch=1)
        set_podt = QPushButton("🖼 Подтверждение шаблони")
        set_podt.setToolTip("Бир марта юкланади — ҳамма адресга ишлайди")
        set_podt.clicked.connect(self._set_podt)
        podt_row.addWidget(set_podt)
        arrange_podt = QPushButton("📐 Подтверждение матнлари")
        arrange_podt.clicked.connect(self._arrange_podt)
        podt_row.addWidget(arrange_podt)
        root.addLayout(podt_row)

        # -- the two photographs ---------------------------------------
        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        docs.addWidget(self._passport)
        self._patent = DropZone("🩷", "Патент (русча ФИО учун)")
        docs.addWidget(self._patent)
        root.addLayout(docs)

        # -- dates + code ----------------------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)

        grid.addWidget(QLabel("Бошланиши:"), 0, 0)
        self._from = QDateEdit(QDate.currentDate())
        self._from.setCalendarPopup(True)
        self._from.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._from, 0, 1)
        grid.addWidget(QLabel("Тугаши:"), 0, 2)
        self._to = QDateEdit(QDate.currentDate().addMonths(3))
        self._to.setCalendarPopup(True)
        self._to.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._to, 0, 3)

        grid.addWidget(QLabel("Уведомление № (код):"), 1, 0)
        self._code = QLineEdit()
        self._code.setPlaceholderText("масалан 02/770-152/26/156651")
        grid.addWidget(self._code, 1, 1, 1, 3)

        # -- the dormitory address (with its host) ---------------------
        addr_head = QHBoxLayout()
        addr_head.addWidget(QLabel("Адрес (йотоқхона):"))
        history = QPushButton("📋 Сақланганлар")
        history.clicked.connect(self._show_addresses)
        addr_head.addWidget(history)
        addr_head.addStretch(1)
        root.addLayout(addr_head)

        addr = QGridLayout()
        addr.setHorizontalSpacing(10)
        addr.setVerticalSpacing(8)
        root.addLayout(addr)
        self._subject = self._line(addr, 0, 0, "Субъект (ГОРОД МОСКВА):")
        self._district = self._line(addr, 0, 2, "Район:")
        self._punkt = self._line(addr, 1, 0, "Насел. пункт (бўлса):")
        self._street = self._line(addr, 1, 2, "Кўча (УЛ …):")
        self._dom = self._line(addr, 2, 0, "Дом:")
        self._korpus = self._line(addr, 2, 2, "Корпус:")
        self._kvartira = self._line(addr, 3, 0, "Квартира:")
        self._host_surname = self._line(addr, 4, 0, "Қабул қилувчи фамилия:")
        self._host_name = self._line(addr, 4, 2, "Исми:")
        self._host_patronymic = self._line(addr, 5, 0, "Отчество:")

        # -- run --------------------------------------------------------
        run_row = QHBoxLayout()
        self._run = QPushButton("🖨 Тайёрлаш")
        self._run.setObjectName("primaryButton")
        self._run.clicked.connect(self._generate)
        run_row.addWidget(self._run)
        run_row.addStretch(1)
        root.addLayout(run_row)

        self._progress = RunProgress(self)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)

        self._reload()
        self._restore()
        # Connected only now: _reload() fills the combo, and every item it
        # adds would otherwise fire this and overwrite the address boxes
        # while the list is still being built.
        self._template.currentIndexChanged.connect(self._on_blank)

    # ------------------------------------------------------------ helpers
    def _line(self, grid: QGridLayout, row: int, col: int, label: str) -> QLineEdit:
        grid.addWidget(QLabel(label), row, col)
        edit = QLineEdit()
        grid.addWidget(edit, row, col + 1)
        return edit

    def _reload(self) -> None:
        current = self._template.currentData()
        # Rebuilding the list fires currentIndexChanged for every item added,
        # and each one would overwrite the address boxes the operator may be
        # in the middle of typing. Silence it until the list is whole.
        self._template.blockSignals(True)
        try:
            self._template.clear()
            for blank in self._c.templates():
                self._template.addItem(blank.stem, str(blank))
            if self._template.count() == 0:
                self._template.addItem("— бланка юкланмаган —", None)
            elif current:
                index = self._template.findData(current)
                if index >= 0:
                    self._template.setCurrentIndex(index)
        finally:
            self._template.blockSignals(False)
        podt = self._c.podt_template()
        self._podt_state.setText(
            "🖼 Подтверждение шаблони: юкланган ✅" if podt
            else "🖼 Подтверждение шаблони: ҳали юкланмаган ⚠️")

    def _restore(self) -> None:
        if not self._blank_address():
            known = self._c.addresses()
            if known:
                self._apply_address(known[0])

    def _blank_address(self) -> bool:
        """The address this blank was last registered on, put back in place.

        The office keeps one blank per dormitory, so choosing the blank all
        but names the address — «бланка танлаганимда ўша бланка билан охирги
        марта ишлатган адрес автоматик чиқсин». It is filled in, not locked:
        typing over it is what changes it, and what is typed is what is used.
        """
        entry = self._c.address_for_blank(self._template.currentData())
        if not entry:
            return False
        self._apply_address(entry)
        self._status.setText(
            f"📍 Бу бланканинг адреси: {self._c.address_label(entry)} "
            "— ўзгартирмасангиз шунга қилинади.")
        return True

    def _on_blank(self) -> None:
        """A different blank was picked — bring its own address back."""
        self._blank_address()

    def _apply_address(self, entry: dict) -> None:
        self._subject.setText(str(entry.get("addr_subject") or ""))
        self._district.setText(str(entry.get("addr_district") or ""))
        self._punkt.setText(str(entry.get("addr_punkt") or ""))
        self._street.setText(str(entry.get("addr_street") or ""))
        self._dom.setText(str(entry.get("dom") or ""))
        self._korpus.setText(str(entry.get("korpus") or ""))
        self._kvartira.setText(str(entry.get("kvartira") or ""))
        self._code.setText(str(entry.get("code") or ""))
        self._host_surname.setText(str(entry.get("host_surname") or ""))
        self._host_name.setText(str(entry.get("host_name") or ""))
        self._host_patronymic.setText(str(entry.get("host_patronymic") or ""))

    def _show_addresses(self) -> None:
        known = self._c.addresses()
        if not known:
            self._warn("Ҳали адрес йўқ — биринчисини ёзинг, ўзи сақланади.")
            return
        menu = QMenu(self)
        for entry in known:
            label = str(entry.get("label") or entry.get("addr_street") or "?")
            menu.addAction(label, lambda e=entry: self._apply_address(e))
        menu.exec(self.mapToGlobal(self._subject.geometry().bottomLeft()))

    # ------------------------------------------------------------ blanks
    def _add_template(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "2 саҳифали бланкани танланг", "", "Бланка (*.pdf)")
        if not source:
            return
        name, ok = QInputDialog.getText(self, "Бланка номи", "Ном беринг:")
        if not ok or not name.strip():
            return
        try:
            dest = self._c.add_template(name.strip(), Path(source))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._template.setCurrentIndex(self._template.findData(str(dest)))

    def _remove_template(self) -> None:
        template = self._template.currentData()
        if not template:
            return
        if QMessageBox.question(self, "Ўчириш", "Бланка ўчирилсинми?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_template(Path(template))
        self._reload()

    def _set_podt(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "Подтверждение шаблонини танланг", "", "Шаблон (*.pdf)")
        if not source:
            return
        try:
            self._c.set_podt_template(Path(source))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._status.setText("✅ Подтверждение шаблони сақланди — энди ҳамма "
                             "адресга ишлайверади.")

    # ------------------------------------------------------------ arrange
    def _sample(self):
        from datetime import date

        from src.pdf.qrreg_renderer import QrRegData

        return QrRegData(
            surname="ИБАДУЛЛАЕВ", name="АНВАР", patronymic="ОЙБЕК УГЛИ",
            citizenship="УЗБЕКИСТАН", birth_date=date(2004, 6, 17),
            gender="male", pass_series="FA", pass_number="3028791",
            pass_issued=date(2021, 6, 9), pass_expiry=date(2031, 6, 8),
            valid_from=date(2026, 7, 21), valid_to=date(2026, 10, 18),
            addr_subject="ГОРОД МОСКВА", addr_district="ОБРУЧЕВСКИЙ РАЙОН",
            addr_street="УЛ НОВАТОРОВ", dom="34", korpus="3", kvartira="50",
            code="02/770-152/26/156651",
            host_surname="АЛЕКСАНДРОВА", host_name="НИНА",
            host_patronymic="ВЛАДИМИРОВНА")

    def _arrange_reg(self) -> None:
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани танланг ёки юкланг.")
            return
        from src.pdf.qrreg_renderer import reg_values
        from src.pdf.qrreg_spec import REG_SLOTS

        self._arrange(Path(template), REG_SLOTS, reg_values(self._sample()),
                      self._c.layout(Path(template)),
                      lambda fields: self._c.save_layout(
                          Path(template), {"fields": fields}))

    def _arrange_podt(self) -> None:
        template = self._c.podt_template()
        if template is None:
            self._warn("Аввал подтверждение шаблонини юкланг.")
            return
        from src.pdf.qrreg_renderer import podt_values
        from src.pdf.qrreg_spec import PODT_SLOTS

        self._arrange(template, PODT_SLOTS, podt_values(self._sample()),
                      self._c.podt_layout(),
                      lambda fields: self._c.save_podt_layout(
                          {"fields": fields}),
                      font_family="Arial")

    def _arrange(self, template: Path, base_slots, sample, layout, save,
                 font_family: str = "Times New Roman") -> None:
        import fitz

        from src.ui.widgets.layout_editor import Item
        from src.ui.widgets.multipage_layout_editor import MultiPageLayoutEditor

        try:
            pages = []
            with fitz.open(str(template)) as doc:
                for page in doc:
                    pages.append(page.get_pixmap(dpi=110).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        moved = (layout or {}).get("fields") or {}
        items_by_page: dict[int, list[Item]] = {}
        for key, slot in base_slots.items():
            if slot.page > len(pages):
                continue
            x, baseline, size = slot.x, slot.baseline, slot.size
            if key in moved and len(moved[key]) == 3:
                x, baseline, size = (float(v) for v in moved[key])
            items_by_page.setdefault(slot.page, []).append(
                Item(key=key, label=key, sample=sample.get(key) or key,
                     x=x, baseline=baseline, size=size,
                     font_family=font_family))
        dialog = MultiPageLayoutEditor(pages, items_by_page,
                                       title="КРКОД РЕГ", parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            save(dialog.result().items)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText("✅ Матн жойлари сақланди.")

    # ------------------------------------------------------------ printing
    def _generate(self) -> None:
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани юкланг.")
            return
        if self._passport.path is None:
            self._warn("Паспорт расмини ташланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return

        passport = Path(self._passport.path).read_bytes()
        patent = (Path(self._patent.path).read_bytes()
                  if self._patent.path is not None else None)
        valid_from = self._from.date().toPython()
        valid_to = self._to.date().toPython()
        code = self._code.text().strip()
        address = {
            "addr_subject": self._subject.text(),
            "addr_district": self._district.text(),
            "addr_punkt": self._punkt.text(),
            "addr_street": self._street.text(),
            "dom": self._dom.text(), "korpus": self._korpus.text(),
            "kvartira": self._kvartira.text(),
            "host_surname": self._host_surname.text(),
            "host_name": self._host_name.text(),
            "host_patronymic": self._host_patronymic.text()}

        self._run.setEnabled(False)
        self._progress.start("Ҳужжатлар ўқилиб, QR тайёрланаяпти…")

        def work():
            worker = self._c.read_documents(passport, patent)
            return self._c.generate(template=Path(template), passport=worker,
                                    valid_from=valid_from, valid_to=valid_to,
                                    address=address, code=code)

        run_async(work, on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._status.setText(f"✅ Рабочий столга сақланди: {result.saved.name}\n"
                             f"🔗 {result.link}")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
