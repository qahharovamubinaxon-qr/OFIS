"""ТРУДАВОЙ/УВЕДОМЛЕНИЕ — the eight firms, one press, both papers.

Passport + patent in, the firm picked, the date set — the ТД and the УВ
come out as the firm's own documents with only the worker changed. Every
text on every page can be dragged and resized against the firm's blank.
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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.trud8_controller import Trud8Controller
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

_PROFESSIONS = ("ПОДСОБНЫЙ РАБОЧИЙ", "РАЗНОРАБОЧИЙ", "УБОРЩИЦА", "КУРЬЕР",
                "МОНТАЖНИК", "ШТУКАТУР", "БЕТОНЩИК", "МАЛЯР")


class Trud8View(QWidget):
    def __init__(self, controller: Trud8Controller) -> None:
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

        title = QLabel("ТРУДАВОЙ + УВЕДОМЛЕНИЕ — 8 фирма")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        firm_row = QHBoxLayout()
        firm_row.addWidget(QLabel("Фирма:"))
        self._firm = QComboBox()
        firm_row.addWidget(self._firm, stretch=1)
        add_firm = QPushButton("➕ Фирма")
        add_firm.clicked.connect(self._add_firm)
        firm_row.addWidget(add_firm)
        set_uv = QPushButton("➕ УВ")
        set_uv.setToolTip("Танланган фирмага УВ бланкасини юклаш")
        set_uv.clicked.connect(self._set_uv)
        firm_row.addWidget(set_uv)
        drop = QPushButton("🗑")
        drop.clicked.connect(self._remove_firm)
        firm_row.addWidget(drop)
        arrange_td = QPushButton("📐 ТД")
        arrange_td.setToolTip("ТД матнларини суриш/размерлаш — ҳар варақда")
        arrange_td.clicked.connect(lambda: self._arrange("td"))
        firm_row.addWidget(arrange_td)
        arrange_uv = QPushButton("📐 УВ")
        arrange_uv.clicked.connect(lambda: self._arrange("uv"))
        firm_row.addWidget(arrange_uv)
        root.addLayout(firm_row)

        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        docs.addWidget(self._passport)
        self._front = DropZone("🩷", "Патент олди")
        docs.addWidget(self._front)
        self._back = DropZone("🩶", "Патент орқаси")
        docs.addWidget(self._back)
        root.addLayout(docs)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)
        grid.addWidget(QLabel("Шартнома санаси:"), 0, 0)
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._date, 0, 1)
        grid.addWidget(QLabel("Должность (бўш — патентдан):"), 0, 2)
        self._profession = QComboBox()
        self._profession.setEditable(True)
        self._profession.addItem("")
        self._profession.addItems(_PROFESSIONS)
        grid.addWidget(self._profession, 0, 3)

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
        current = self._firm.currentData()
        self._firm.clear()
        for firm in self._c.firms():
            self._firm.addItem(firm.name, str(firm))
        if self._firm.count() == 0:
            self._firm.addItem("— фирма йўқ —", None)
        elif current:
            index = self._firm.findData(current)
            if index >= 0:
                self._firm.setCurrentIndex(index)

    # ------------------------------------------------------------- firms
    def _add_firm(self) -> None:
        name, ok = QInputDialog.getText(self, "Янги фирма", "Фирма номи:")
        if not ok or not name.strip():
            return
        td, _ = QFileDialog.getOpenFileName(
            self, "ТД бланкаси (Word/PDF)", "", "Бланка (*.docx *.pdf)")
        if not td:
            return
        uv, _ = QFileDialog.getOpenFileName(
            self, "УВ бланкаси (Word/PDF, ихтиёрий — Бекор = ўтказиш)", "",
            "Бланка (*.docx *.pdf)")
        try:
            self._c.add_firm(name.strip(), Path(td),
                             Path(uv) if uv else None)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._status.setText(f"✅ «{name.strip()}» қўшилди — жойларини "
                             "«📐 ТД / 📐 УВ» билан тўғрилаб чиқинг.")

    def _set_uv(self) -> None:
        firm = self._firm.currentData()
        if not firm:
            return
        uv, _ = QFileDialog.getOpenFileName(
            self, "УВ бланкаси (Word/PDF)", "", "Бланка (*.docx *.pdf)")
        if not uv:
            return
        try:
            self._c.set_uv(Path(firm), Path(uv))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText("✅ УВ бланкаси юкланди.")

    def _remove_firm(self) -> None:
        firm = self._firm.currentData()
        if not firm:
            return
        if QMessageBox.question(
                self, "Ўчириш",
                f"«{Path(firm).name}» фирмаси ўчирилсинми?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_firm(Path(firm))
        self._reload()

    # ----------------------------------------------------------- arrange
    def _arrange(self, kind: str) -> None:
        firm = self._firm.currentData()
        if not firm:
            self._warn("Аввал фирмани танланг.")
            return
        from datetime import date as _date

        import fitz

        from src.pdf.trud8_renderer import Trud8Data, values
        from src.ui.widgets.layout_editor import Item
        from src.ui.widgets.multipage_layout_editor import MultiPageLayoutEditor

        if (Path(firm) / f"{kind}.docx").exists():
            self._warn("Бу фирма Word бланкали — жойлаш керак эмас: формат "
                       "ўзи жойлайди, натижа Word файл бўлиб чиқади.")
            return
        template = Path(firm) / f"{kind}.pdf"
        if not template.exists():
            self._warn("Бу фирмада бундай бланка йўқ — «➕ УВ» билан юкланг.")
            return
        slots = self._c.slots(Path(firm), kind)
        try:
            pages = []
            with fitz.open(str(template)) as doc:
                for page in doc:
                    pages.append(page.get_pixmap(dpi=100).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        sample = values(Trud8Data(
            surname="ХУРСАНОВ", name="МИРШОЯД", patronymic="ЗОХИДЖОН УГЛИ",
            citizenship="УЗБЕКИСТАН", birth_date=_date(1995, 5, 1),
            gender="male", pass_series="FB", pass_number="0826891",
            pass_issued=_date(2025, 2, 22), pass_issued_by="МВД 3206",
            pat_series="47", pat_number="2500044825",
            pat_blank_series="ПР", pat_blank_number="5094937",
            pat_issued=_date(2025, 6, 1),
            profession="Разнорабочий", deal_date=_date(2026, 7, 1)))
        moved = (self._c.layout(Path(firm), kind) or {}).get("fields") or {}
        items_by_page: dict[int, list[Item]] = {}
        for index, slot in enumerate(slots):
            key = f"{slot['key']}#{index}"
            x, baseline, size = slot["x"], slot["baseline"], slot["size"]
            if key in moved and len(moved[key]) == 3:
                x, baseline, size = (float(v) for v in moved[key])
            items_by_page.setdefault(slot["page"], []).append(
                Item(key=key, label=slot["key"],
                     sample=sample.get(slot["key"]) or slot["key"],
                     x=x, baseline=baseline, size=size,
                     font_family=("Times New Roman" if slot.get("serif")
                                  else "Calibri")))
        if not items_by_page:
            self._warn("Бу бланкада харита йўқ.")
            return
        dialog = MultiPageLayoutEditor(pages, items_by_page,
                                       title=f"ТРУД {kind.upper()}",
                                       parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.save_layout(Path(firm), kind,
                                {"fields": dialog.result().items})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText("✅ Матн жойлари сақланди.")

    # ---------------------------------------------------------- printing
    def _generate(self) -> None:
        firm = self._firm.currentData()
        if not firm:
            self._warn("Аввал фирмани танланг.")
            return
        if self._passport.path is None or self._front.path is None:
            self._warn("Паспорт ва патент олди расмларини ташланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        passport = Path(self._passport.path).read_bytes()
        front = Path(self._front.path).read_bytes()
        back = (Path(self._back.path).read_bytes()
                if self._back.path is not None else None)
        when = self._date.date().toPython()
        profession = self._profession.currentText().strip()

        self._run.setEnabled(False)
        self._progress.start("Ҳужжатлар ўқилиб, ТД ва УВ тайёрланаяпти…")

        def work():
            read_passport, read_patent = self._c.read_documents(
                passport, front, back)
            return self._c.generate(
                firm=Path(firm), passport=read_passport, patent=read_patent,
                profession=profession, deal_date=when)

        run_async(work, on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        names = ", ".join(p.name for p in result.saved)
        self._status.setText(f"✅ Тайёр: {names}")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "trud"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
