"""КУК ЧЕК — the payment чек: patent in, date and sum picked, чек out."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QColorDialog,
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
from src.controllers.kukchek_controller import KukChekController
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class KukChekView(QWidget):
    def __init__(self, controller: KukChekController) -> None:
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

        title = QLabel("КУК ЧЕК — тўлов чеки (СФЕРА)")
        title.setObjectName("viewTitle")
        root.addWidget(title)

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
        arrange = QPushButton("📐 Матн ва печатни жойлаш")
        arrange.clicked.connect(self._arrange)
        blank_row.addWidget(arrange)
        style = QPushButton("🎨 Ранг ва қалинлик")
        style.setToolTip("Ҳар матннинг рангини ва қалин/юпқалигини танлаш")
        style.clicked.connect(self._style)
        blank_row.addWidget(style)
        root.addLayout(blank_row)

        stamp_row = QHBoxLayout()
        self._stamp_state = QLabel("")
        stamp_row.addWidget(self._stamp_state, stretch=1)
        set_stamp = QPushButton("⚙ Печать юклаш")
        set_stamp.setToolTip("Оқ фони ўзи шаффоф бўлади")
        set_stamp.clicked.connect(self._set_stamp)
        stamp_row.addWidget(set_stamp)
        drop_stamp = QPushButton("🗑 Печать")
        drop_stamp.clicked.connect(self._remove_stamp)
        stamp_row.addWidget(drop_stamp)
        root.addLayout(stamp_row)

        docs = QHBoxLayout()
        self._patent = DropZone("🩷", "Патент картаси")
        docs.addWidget(self._patent)
        root.addLayout(docs)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)
        grid.addWidget(QLabel("Число (тўлов санаси):"), 0, 0)
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._date, 0, 1)
        grid.addWidget(QLabel("Сумма (сўм эмас — рубл):"), 0, 2)
        self._amount = QLineEdit()
        self._amount.setPlaceholderText("масалан 23600")
        grid.addWidget(self._amount, 0, 3)

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
        self._stamp_state.setText(
            "⚙ Печать: юкланган ✅" if self._c.stamp()
            else "⚙ Печать: ҳали юкланмаган (ихтиёрий)")

    # ------------------------------------------------------------ blanks
    def _add_template(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "Чек бланкасини танланг", "",
            "Бланка (*.pdf *.jpg *.jpeg *.png)")
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
        self._status.setText(
            f"✅ «{dest.stem}» юкланди — жойларини «📐» билан текширинг.")

    def _remove_template(self) -> None:
        template = self._template.currentData()
        if not template:
            return
        if QMessageBox.question(self, "Ўчириш", "Бланка ўчирилсинми?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_template(Path(template))
        self._reload()

    def _set_stamp(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "Печать расмини танланг", "", "Расм (*.png *.jpg *.jpeg)")
        if not source:
            return
        try:
            self._c.set_stamp(Path(source))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._status.setText("✅ Печать сақланди — «📐» да суриш мумкин.")

    def _remove_stamp(self) -> None:
        self._c.remove_stamp()
        self._reload()

    # ----------------------------------------------------------- arrange
    def _arrange(self) -> None:
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани танланг ёки юкланг.")
            return
        from datetime import date as _date
        from datetime import datetime as _dt

        import fitz

        from src.pdf.kukchek_renderer import (
            IMG_LABELS,
            IMG_SLOTS,
            SLOTS,
            KukChekData,
            values,
        )
        from src.ui.widgets.layout_editor import Item
        from src.ui.widgets.multipage_layout_editor import MultiPageLayoutEditor

        template = Path(template)
        try:
            with fitz.open(str(template)) as raw:
                doc = (raw if raw.is_pdf
                       else fitz.open("pdf", raw.convert_to_pdf()))
                pages = [doc[0].get_pixmap(dpi=110).tobytes("png")]
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        sample = values(KukChekData(
            fam="КАХХАРОВ", ism="КАХРАМОН", otch="АБДИСАТТОР УГЛИ",
            inn="540963187924", when=_date(2026, 7, 30),
            at=_dt(2026, 7, 30, 10, 54, 53), rubles=13578, kopecks=0),
            uip="10466146320086093007202611948663")
        moved = (self._c.layout(template) or {}).get("fields") or {}
        items = []
        for key, slot in {**SLOTS, **IMG_SLOTS}.items():
            x, baseline, size = slot.x, slot.baseline, slot.size
            if key in moved and len(moved[key]) == 3:
                x, baseline, size = (float(v) for v in moved[key])
            items.append(Item(key=key, label=key,
                              sample=IMG_LABELS.get(key)
                              or sample.get(key) or key,
                              x=x, baseline=baseline, size=size,
                              font_family="Courier New"))
        dialog = MultiPageLayoutEditor(pages, {1: items},
                                       title="КУК ЧЕК", parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.save_layout(template, {"fields": dialog.result().items})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText("✅ Матн ва печать жойлари сақланди.")

    def _style(self) -> None:
        """Colour and weight, per text — kept beside this blank."""
        from PySide6.QtWidgets import QInputDialog

        from src.pdf.kukchek_renderer import SLOTS, placed

        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани танланг ёки юкланг.")
            return
        template = Path(template)
        picked, ok = QInputDialog.getItem(
            self, "КУК ЧЕК", "Қайси матн?", list(SLOTS), 0, False)
        if not ok:
            return
        colour = QColorDialog.getColor(parent=self, title="Матн ранги")
        if not colour.isValid():
            return
        weight, ok = QInputDialog.getItem(
            self, "КУК ЧЕК", "Қалинлиги", ["Қалин (жирний)", "Юпқа (оддий)"],
            0, False)
        if not ok:
            return
        kept = self._c.layout(template)
        styles = dict(kept.get("styles") or {})
        styles[picked] = {
            "colour": [colour.redF(), colour.greenF(), colour.blueF()],
            "bold": weight.startswith("Қалин")}
        try:
            self._c.save_layout(template, {"styles": styles})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        was = placed(kept, SLOTS)[picked]
        self._status.setText(
            f"✅ «{picked}»: ранг ва қалинлик сақланди "
            f"({'қалин' if styles[picked]['bold'] else 'юпқа'}; "
            f"аввалгиси {'қалин' if was.bold else 'юпқа'}).")

    # ---------------------------------------------------------- printing
    def _generate(self) -> None:
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани юкланг.")
            return
        if self._patent.path is None:
            self._warn("Патент картасининг расмини ташланг.")
            return
        if not self._amount.text().strip():
            self._warn("Суммани киритинг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        patent = Path(self._patent.path).read_bytes()
        when = self._date.date().toPython()
        amount = self._amount.text().strip()

        self._run.setEnabled(False)
        self._progress.start("Патент ўқилиб, чек тайёрланаяпти…")

        def work():
            fields = self._c.read_patent(patent)
            return self._c.generate(template=Path(template), fields=fields,
                                    when=when, amount_text=amount)

        run_async(work, on_success=self._done, on_error=self._failed)

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

        folder = paths.output_dir() / "kukchek"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
