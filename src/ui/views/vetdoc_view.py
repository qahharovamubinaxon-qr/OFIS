"""МЕРКУРИЙ — дўкон маълумотномаси: ҳужжат расмлари → шакл → PDF + сайт.

Иш тартиби: ҳужжат расмларини ташлаш → «🤖 AI ўқиш» майдонларни тўлдиради →
оператор текширади ва тўғрилайди → «🖨 Тайёрлаш» бланкани PDF қилади, ёзувни
сақлайди ва сайт саҳифасини ясайди. Бланкадаги QR ўша саҳифага олиб боради.

Майдонлар реестрдаги кўринишнинг ўзи — шунинг учун улар кўп. Шакл бўлимларга
бўлинган ва ўралади; тўлдирилмагани бланкада босилмайди, фақат сайтда
кўринади.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.common.threading import run_async
from src.controllers.vetdoc_controller import VetDocController
from src.domain.vetdoc import Animal, DocRef, Shop, Treatment, VetRecord
from src.services.vetdoc_service import VetDocResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)

STATUSES = ("оформлен", "погашен", "аннулирован")

#: Шакл бўлимлари: (бўлим номи, ((майдон, ёрлиқ, эслатма), …)).
SECTIONS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    ("Общие сведения", (
        ("number", "Номер справки", "MR-2026-000142"),
        ("accounting", "Учёт", "учтён в журнале магазина"),
        ("made_by", "Способ оформления", "оформлено в программе OFIS"),
        ("blank_no", "Номер бланка", ""),
    )),
    ("Информация о продукции", (
        ("kind", "Тип продукции", "Живые животные"),
        ("product", "Продукция", "птица"),
        ("species", "Вид продукции", "курица (0105)"),
        ("title", "Наименование продукции", "Петух"),
        ("volume", "Объём", "4 головы"),
        ("batch", "Номер производственной партии", "б/н"),
        ("birth", "Дата рождения", "Январь 2026"),
        ("wellbeing", "Благополучие местности", "благополучна"),
        ("purpose", "Направление", "содержание"),
        ("held_since", "Животные содержались", ""),
        ("quarantine_place", "Место для карантинирования", ""),
        ("quarantine_days", "Дней карантинирования", ""),
        ("notes", "Особые отметки", "клинически здоровы"),
        ("incoming_doc", "Номер и дата входящего документа", ""),
        ("production_doc", "Номер и дата производственного документа", ""),
        ("remark", "Примечание", ""),
    )),
    ("Транспорт и происхождение", (
        ("transaction", "Тип транзакции", "продажа"),
        ("transport", "Тип транспорта", ""),
        ("storage", "Способ хранения при перевозке", ""),
        ("origin_country", "Страна происхождения", "Россия"),
        ("produced_by", "Выработана / выращены", ""),
        ("production_name", "Наименование при производстве", ""),
        ("origin_doc", "Документ о происхождении", ""),
    )),
    ("Отправитель и получатель", (
        ("sender_company", "Отправитель — предприятие", "ўзи: дўкон номи"),
        ("sender_subject", "Отправитель — хоз. субъект", ""),
        ("receiver_company", "Получатель — предприятие", "частное лицо"),
        ("receiver_subject", "Получатель — хоз. субъект", ""),
        ("buyer", "Покупатель (Ф.И.О.)", "Иванов Иван Иванович"),
    )),
    ("Оформление", (
        ("institution", "Учреждение", "ўзи: дўкон номи"),
        ("vet_name", "Ф.И.О. ветеринарного врача", ""),
        ("vet_post", "Должность", "ветеринарный врач"),
        ("vet_phone", "Контактный телефон", ""),
    )),
)

ANIMAL_COLS: tuple[tuple[str, str], ...] = (
    ("group_no", "Номер группы"), ("mark", "Маркировка"),
    ("farm_no", "Внутрихоз. №"), ("nickname", "Кличка"), ("sex", "Пол"),
    ("breed", "Порода"), ("age", "Возраст"), ("weight", "Вес, кг"),
    ("count", "Кол-во"), ("note", "Примечание"),
)
TREATMENT_COLS: tuple[tuple[str, str], ...] = (
    ("kind", "Тип"), ("name", "Наименование"), ("done", "Дата"),
    ("drug", "Препарат и производитель"), ("series", "Серия"),
    ("until", "Действует до"),
)
DOC_COLS: tuple[tuple[str, str], ...] = (
    ("series", "Серия"), ("number", "Номер"), ("issued", "Дата выдачи"),
    ("kind", "Тип документа"),
)


class _Table(QGroupBox):
    """Қўшиш/ўчириш тугмали оддий жадвал — ҳайвонлар, ишлов, ҳужжатлар."""

    def __init__(self, title: str, columns: tuple[tuple[str, str], ...],
                 factory) -> None:
        super().__init__(title)
        self._columns = columns
        self._factory = factory
        root = QVBoxLayout(self)
        self._table = QTableWidget(0, len(columns))
        self._table.setHorizontalHeaderLabels([label for _, label in columns])
        self._table.verticalHeader().setVisible(False)
        self._table.setMinimumHeight(110)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self._table)

        buttons = QHBoxLayout()
        add = QPushButton("+ қатор")
        add.clicked.connect(lambda: self.add_row())
        remove = QPushButton("− қаторни ўчириш")
        remove.clicked.connect(self._remove_row)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        root.addLayout(buttons)

    def add_row(self, values: dict[str, str] | None = None) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for index, (key, _label) in enumerate(self._columns):
            text = str((values or {}).get(key, "") or "")
            self._table.setItem(row, index, QTableWidgetItem(text))

    def _remove_row(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)

    def clear_rows(self) -> None:
        self._table.setRowCount(0)

    def first_row_values(self) -> dict[str, str]:
        if self._table.rowCount() == 0:
            return {}
        return {key: (self._table.item(0, i).text() if self._table.item(0, i)
                      else "")
                for i, (key, _label) in enumerate(self._columns)}

    def set_first_row(self, values: dict[str, str]) -> None:
        """AI ўқиганини биринчи қаторга қўяди — бор қиймат ўчирилмайди."""
        if self._table.rowCount() == 0:
            self.add_row()
        for index, (key, _label) in enumerate(self._columns):
            text = str(values.get(key, "") or "")
            if not text:
                continue
            item = self._table.item(0, index)
            if item is None or not item.text().strip():
                self._table.setItem(0, index, QTableWidgetItem(text))

    def objects(self) -> list:
        made = []
        for row in range(self._table.rowCount()):
            values = {}
            for index, (key, _label) in enumerate(self._columns):
                item = self._table.item(row, index)
                values[key] = item.text().strip() if item else ""
            if any(values.values()):
                made.append(self._factory(**values))
        return made


class VetDocView(QWidget):
    def __init__(self, controller: VetDocController) -> None:
        super().__init__()
        self._c = controller
        self._fields: dict[str, QLineEdit] = {}
        self._last: VetDocResult | None = None

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

        title = QLabel("МЕРКУРИЙ — справка о продаже и ветобработке")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        hint = QLabel(
            "Ҳужжат расмларини ташланг → «🤖 AI ўқиш» майдонларни тўлдиради → "
            "текшириб тўғриланг → «🖨 Тайёрлаш». Бланка PDF бўлади, ёзув сайт "
            "саҳифасига тушади, QR ўша саҳифани очади.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a94a3;")
        root.addWidget(hint)

        root.addWidget(self._shop_box())
        root.addWidget(self._read_box())

        self._progress = RunProgress()
        root.addWidget(self._progress)

        head = QGroupBox("Справка")
        grid = QGridLayout(head)
        grid.addWidget(QLabel("Дата оформления:"), 0, 0)
        self._issued = QDateEdit(QDate.currentDate())
        self._issued.setCalendarPopup(True)
        self._issued.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._issued, 0, 1)
        grid.addWidget(QLabel("Статус:"), 0, 2)
        self._status = QComboBox()
        self._status.addItems(STATUSES)
        grid.addWidget(self._status, 0, 3)
        root.addWidget(head)

        for name, fields in SECTIONS:
            root.addWidget(self._section(name, fields))

        self._animals = _Table("Опись живых животных", ANIMAL_COLS, Animal)
        self._animals.add_row()
        root.addWidget(self._animals)
        self._treatments = _Table("Иммунизация и обработка против паразитов",
                                  TREATMENT_COLS, Treatment)
        root.addWidget(self._treatments)
        self._docs = _Table("Сопроводительные документы", DOC_COLS, DocRef)
        root.addWidget(self._docs)

        actions = QHBoxLayout()
        self._run = QPushButton("🖨  Тайёрлаш (PDF + саҳифа)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._publish)
        actions.addWidget(self._run)
        site = QPushButton("🌐 Сайт папкаси")
        site.clicked.connect(self._open_site)
        actions.addWidget(site)
        export = QPushButton("📤 Сайтни чиқариш")
        export.clicked.connect(self._export_site)
        actions.addWidget(export)
        clear = QPushButton("🧹 Тозалаш")
        clear.clicked.connect(self._clear)
        actions.addWidget(clear)
        actions.addStretch(1)
        root.addLayout(actions)

        self._status_label = QLabel(self._hint())
        self._status_label.setWordWrap(True)
        self._status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction)
        self._status_label.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status_label)
        root.addStretch(1)

        self._load_shop()

    # ------------------------------------------------------------ қисмлар
    def _shop_box(self) -> QGroupBox:
        box = QGroupBox("Дўкон (бир марта тўлдирилади)")
        grid = QGridLayout(box)
        self._shop_fields: dict[str, QLineEdit] = {}
        spec = (("name", "Номи (логотип ёнида)", "МЕРКУРИЙ"),
                ("legal", "Тўлиқ номи / ИП", 'ИП "МЕРКУРИЙ"'),
                ("address", "Манзил", ""),
                ("phone", "Телефон", ""),
                ("site", "Сайт манзили (QR шу ерга қарайди)",
                 "https://nomingiz.github.io/merkuriy"),
                ("inn", "ИНН", ""))
        for index, (key, label, placeholder) in enumerate(spec):
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            self._shop_fields[key] = edit
            grid.addWidget(QLabel(label + ":"), index // 2, (index % 2) * 2)
            grid.addWidget(edit, index // 2, (index % 2) * 2 + 1)

        buttons = QHBoxLayout()
        save = QPushButton("💾 Дўконни сақлаш")
        save.clicked.connect(self._save_shop)
        buttons.addWidget(save)
        logo = QPushButton("🖼 Логотип юклаш")
        logo.clicked.connect(self._pick_logo)
        buttons.addWidget(logo)
        self._logo_label = QLabel("")
        self._logo_label.setStyleSheet("color:#8a94a3;")
        buttons.addWidget(self._logo_label)
        buttons.addStretch(1)
        grid.addLayout(buttons, len(spec) // 2 + 1, 0, 1, 4)
        return box

    def _read_box(self) -> QGroupBox:
        box = QGroupBox("Ҳужжат расмлари (AI ўқийди)")
        row = QHBoxLayout(box)
        self._drop = DropZone("📄", "Ҳужжат расмлари / PDF",
                              multiple=True,
                              extensions={".jpg", ".jpeg", ".png", ".webp",
                                          ".pdf"})
        row.addWidget(self._drop, stretch=2)
        side = QVBoxLayout()
        read = QPushButton("🤖 AI ўқиш")
        read.clicked.connect(self._read)
        side.addWidget(read)
        side.addStretch(1)
        row.addLayout(side, stretch=1)
        return box

    def _section(self, name: str,
                 fields: tuple[tuple[str, str, str], ...]) -> QGroupBox:
        box = QGroupBox(name)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        for key, label, placeholder in fields:
            edit = QLineEdit()
            if placeholder:
                edit.setPlaceholderText(placeholder)
            self._fields[key] = edit
            form.addRow(label + ":", edit)
        return box

    # -------------------------------------------------------------- дўкон
    def _load_shop(self) -> None:
        shop = self._c.shop()
        for key, edit in self._shop_fields.items():
            edit.setText(getattr(shop, key, "") or "")
        logo = self._c.logo()
        self._logo_label.setText("логотип: " + (logo.name if logo else "йўқ"))

    def _save_shop(self) -> None:
        shop = Shop(**{key: edit.text().strip()
                       for key, edit in self._shop_fields.items()})
        self._c.save_shop(shop)
        self._status_label.setText("✅ Дўкон маълумоти сақланди.")

    def _pick_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Логотип", "", "Расм (*.png *.jpg *.jpeg *.webp)")
        if not path:
            return
        try:
            self._c.set_logo(Path(path))
        except OfisError as exc:
            QMessageBox.warning(self, "Хато", exc.message)
            return
        self._load_shop()
        self._status_label.setText("✅ Логотип юкланди — бланкада чиқади.")

    # --------------------------------------------------------------- ўқиш
    def _hint(self) -> str:
        if self._c.ai_available():
            return ("AI тайёр. Ҳужжат расмини ташлаб «🤖 AI ўқиш» ни босинг, "
                    "ёки майдонларни қўлда тўлдиринг.")
        return ("AI калити йўқ — Созламаларга калит киритинг, ёки майдонларни "
                "қўлда тўлдиринг (бари ишлайди).")

    def _read(self) -> None:
        files = self._drop.paths()
        if not files:
            QMessageBox.warning(self, "Диққат", "Аввал ҳужжат расмини ташланг.")
            return
        if not self._c.ai_available():
            QMessageBox.warning(self, "Диққат", self._hint())
            return
        try:
            images = [self._c.read_image(path) for path in files]
        except OSError as exc:
            QMessageBox.warning(self, "Хато", f"Файл ўқилмади: {exc}")
            return
        self._progress.start("Ҳужжатлар ўқиляпти…")
        self._status_label.setText("⏳ Ҳужжатлар ўқиляпти…")
        run_async(self._c.read_documents, images,
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, found: dict[str, str]) -> None:
        self._progress.finish()
        if not found:
            self._status_label.setText(
                "⚠️ Ҳеч нарса ўқилмади — майдонларни қўлда тўлдиринг.")
            return
        animal = {}
        for key, value in found.items():
            if key.startswith("animal."):
                animal[key.split(".", 1)[1]] = value
            elif key in self._fields and not self._fields[key].text().strip():
                self._fields[key].setText(value)
        if animal:
            self._animals.set_first_row(animal)
        self._status_label.setText(
            f"✅ {len(found)} майдон ўқилди — текшириб, керагини тўғриланг, "
            "кейин «🖨 Тайёрлаш».")

    def _failed(self, error: Exception) -> None:
        self._progress.fail()
        self._run.setEnabled(True)
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status_label.setText("❌ " + message)
        QMessageBox.warning(self, "Хато", message)

    # ----------------------------------------------------------- чиқариш
    def _record(self) -> VetRecord:
        record = VetRecord(**{key: edit.text().strip()
                              for key, edit in self._fields.items()})
        picked = self._issued.date()
        record.issued = date(picked.year(), picked.month(), picked.day())
        record.status = self._status.currentText()
        record.animals = self._animals.objects()
        record.treatments = self._treatments.objects()
        record.docs = self._docs.objects()
        return record

    def _publish(self) -> None:
        record = self._record()
        self._run.setEnabled(False)
        self._progress.start("Маълумотнома тайёрланяпти…")
        self._status_label.setText("⏳ Маълумотнома тайёрланяпти…")
        run_async(self._c.publish, record,
                  on_success=self._done, on_error=self._failed)

    def _done(self, result: VetDocResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        self._last = result
        self._status_label.setText(
            f"✅ Тайёр: {result.pdf.name} · код {result.record.code} · "
            f"ҳавола: {result.link}")
        from src.ui.widgets.save_to import ask_save_dir

        ask_save_dir(self, [result.pdf])
        box = QMessageBox(self)
        box.setWindowTitle("Тайёр")
        box.setText(f"Маълумотнома тайёр:\n{result.pdf}\n\n"
                    f"Код: {result.record.code}\nҲавола: {result.link}")
        open_pdf = box.addButton("Папкани очиш", QMessageBox.ButtonRole.AcceptRole)
        open_page = box.addButton("Саҳифани очиш", QMessageBox.ButtonRole.ActionRole)
        copy = box.addButton("Ҳаволани нусхалаш", QMessageBox.ButtonRole.ActionRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is open_pdf:
            self._open(result.pdf.parent)
        elif clicked is open_page:
            self._open(result.page)
        elif clicked is copy:
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(result.link)

    def _open_site(self) -> None:
        try:
            folder = self._c.site_dir()
        except OfisError as exc:
            QMessageBox.warning(self, "Хато", exc.message)
            return
        self._open(folder)
        self._status_label.setText(
            "🌐 Сайт папкаси янгиланди — шу папкани доменга (ёки GitHub Pages "
            "га) қўйсангиз, QR ишлайди.")

    def _export_site(self) -> None:
        target = QFileDialog.getExistingDirectory(self, "Сайт учун папка")
        if not target:
            return
        folder = self._c.export_site(Path(target))
        self._status_label.setText(f"📤 Сайт чиқарилди: {folder}")

    def _clear(self) -> None:
        for edit in self._fields.values():
            edit.clear()
        for table in (self._animals, self._treatments, self._docs):
            table.clear_rows()
        self._animals.add_row()
        self._drop.clear()
        self._issued.setDate(QDate.currentDate())
        self._status.setCurrentIndex(0)
        self._status_label.setText(self._hint())

    # ------------------------------------------------------------------
    @staticmethod
    def _open(target: Path) -> None:
        import subprocess
        import sys

        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(target)])  # noqa: S603,S607
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", str(target)])  # noqa: S603,S607
        except OSError:
            pass
