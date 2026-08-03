"""ТРУДАВОЙ + УВЕДОМЛЕНИЕ — the office's own blanks, the office's own map.

Nothing is built in. A firm is a name; the office uploads its EMPTY ТД and
УВ PDFs, then adds each text one by one, saying from a list what that text
means (ФИО, паспорт серия, шартнома санаси…), and drags it where it must
print. Colour, weight and face are chosen per text. The worker's papers
then come out on those very blanks.
"""

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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.trud8_controller import Trud8Controller
from src.pdf.trud8_fields import CATALOGUE
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

_PROFESSIONS = ("ПОДСОБНЫЙ РАБОЧИЙ", "РАЗНОРАБОЧИЙ", "УБОРЩИЦА", "КУРЬЕР",
                "МОНТАЖНИК", "ШТУКАТУР", "БЕТОНЩИК", "МАЛЯР")

_KINDS = (("ТД — трудовой договор", "td"), ("УВ — уведомление", "uv"))


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

        title = QLabel("ТРУДАВОЙ + УВЕДОМЛЕНИЕ — ўз бланкангиз, ўз майдонларингиз")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        firm_row = QHBoxLayout()
        firm_row.addWidget(QLabel("Фирма:"))
        self._firm = QComboBox()
        self._firm.currentIndexChanged.connect(lambda _: self._show_state())
        firm_row.addWidget(self._firm, stretch=1)
        add_firm = QPushButton("➕ Фирма")
        add_firm.setToolTip("Фирма номини ёзасиз — бланкаларини кейин юклайсиз")
        add_firm.clicked.connect(self._add_firm)
        firm_row.addWidget(add_firm)
        drop = QPushButton("🗑 Фирма")
        drop.clicked.connect(self._remove_firm)
        firm_row.addWidget(drop)
        root.addLayout(firm_row)

        blank_row = QHBoxLayout()
        blank_row.addWidget(QLabel("Бўш бланка (PDF):"))
        set_td = QPushButton("📄 ТД юклаш")
        set_td.clicked.connect(lambda: self._set_blank("td"))
        blank_row.addWidget(set_td)
        set_uv = QPushButton("📄 УВ юклаш")
        set_uv.clicked.connect(lambda: self._set_blank("uv"))
        blank_row.addWidget(set_uv)
        blank_row.addStretch(1)
        root.addLayout(blank_row)

        field_row = QHBoxLayout()
        field_row.addWidget(QLabel("Матнлар:"))
        add_text = QPushButton("➕ Матн")
        add_text.setToolTip("Бланкага матн қўшиш — рўйхатдан маъносини танлайсиз")
        add_text.clicked.connect(self._add_field)
        field_row.addWidget(add_text)
        drop_text = QPushButton("🗑 Матн")
        drop_text.clicked.connect(self._remove_field)
        field_row.addWidget(drop_text)
        style = QPushButton("🎨 Ранг ва қалинлик")
        style.clicked.connect(self._style_field)
        field_row.addWidget(style)
        arrange_td = QPushButton("📐 ТД")
        arrange_td.setToolTip("ТД матнларини суриш/катта-кичик қилиш — ҳар варақда")
        arrange_td.clicked.connect(lambda: self._arrange("td"))
        field_row.addWidget(arrange_td)
        arrange_uv = QPushButton("📐 УВ")
        arrange_uv.clicked.connect(lambda: self._arrange("uv"))
        field_row.addWidget(arrange_uv)
        field_row.addStretch(1)
        root.addLayout(field_row)

        self._state = QLabel("")
        self._state.setWordWrap(True)
        self._state.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._state)

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
        self._firm.blockSignals(True)
        self._firm.clear()
        for firm in self._c.firms():
            self._firm.addItem(firm.name, str(firm))
        if self._firm.count() == 0:
            self._firm.addItem("— фирма йўқ, «➕ Фирма» —", None)
        elif current:
            index = self._firm.findData(current)
            if index >= 0:
                self._firm.setCurrentIndex(index)
        self._firm.blockSignals(False)
        self._show_state()

    def _show_state(self) -> None:
        firm = self._firm.currentData()
        if not firm:
            self._state.setText("Фирма қўшинг, сўнг унинг бўш ТД ва УВ "
                                "PDF ларини юкланг.")
            return
        firm = Path(firm)
        parts = []
        for label, kind in _KINDS:
            tag = label.split(" ")[0]
            if self._c.blank(firm, kind) is None:
                parts.append(f"{tag}: бланка йўқ")
                continue
            count = len(self._c.fields(firm, kind))
            parts.append(f"{tag}: {self._c.pages(firm, kind)} варақ, "
                         f"{count} та матн")
        self._state.setText(" · ".join(parts))

    def _firm_now(self) -> Path | None:
        firm = self._firm.currentData()
        if not firm:
            self._warn("Аввал фирмани танланг ёки «➕ Фирма» билан қўшинг.")
            return None
        return Path(firm)

    def _pick_kind(self, question: str) -> str | None:
        labels = [label for label, _ in _KINDS]
        picked, ok = QInputDialog.getItem(self, "ТРУДАВОЙ", question, labels,
                                          0, False)
        if not ok:
            return None
        return dict((label, kind) for label, kind in _KINDS)[picked]

    # ------------------------------------------------------------- firms
    def _add_firm(self) -> None:
        name, ok = QInputDialog.getText(self, "Янги фирма", "Фирма номи:")
        if not ok or not name.strip():
            return
        try:
            made = self._c.add_firm(name.strip())
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        index = self._firm.findData(str(made))
        if index >= 0:
            self._firm.setCurrentIndex(index)
        self._status.setText(f"✅ «{made.name}» қўшилди — энди унинг бўш ТД ва "
                             "УВ PDF ларини юкланг.")

    def _remove_firm(self) -> None:
        firm = self._firm_now()
        if firm is None:
            return
        if QMessageBox.question(
                self, "Ўчириш",
                f"«{firm.name}» фирмаси (бланка ва матнлари билан) "
                "ўчирилсинми?") != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_firm(firm)
        self._reload()

    # ------------------------------------------------------------ blanks
    def _set_blank(self, kind: str) -> None:
        firm = self._firm_now()
        if firm is None:
            return
        tag = "ТД" if kind == "td" else "УВ"
        source, _ = QFileDialog.getOpenFileName(
            self, f"{tag} — бўш бланка PDF", "", "Бланка (*.pdf)")
        if not source:
            return
        try:
            self._c.set_blank(firm, kind, Path(source))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._show_state()
        self._status.setText(
            f"✅ {tag} бланкаси юкланди ({self._c.pages(firm, kind)} варақ) — "
            "«➕ Матн» билан майдонларни қўйинг.")

    # ------------------------------------------------------------ fields
    def _add_field(self) -> None:
        firm = self._firm_now()
        if firm is None:
            return
        kind = self._pick_kind("Қайси бланкага?")
        if kind is None:
            return
        pages = self._c.pages(firm, kind)
        if pages == 0:
            self._warn("Аввал шу бланканинг PDF ини юкланг.")
            return
        page = 1
        if pages > 1:
            page, ok = QInputDialog.getInt(self, "Саҳифа",
                                           f"Нечанчи варақ? (1—{pages})",
                                           1, 1, pages)
            if not ok:
                return
        labels = list(CATALOGUE.values())
        picked, ok = QInputDialog.getItem(
            self, "Матн маъноси", "Бу матн ишчининг қайси маълумоти?",
            labels, 0, False)
        if not ok:
            return
        key = [k for k, v in CATALOGUE.items() if v == picked][0]
        try:
            self._c.add_field(firm, kind, key, page)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._show_state()
        self._status.setText(
            f"✅ «{picked}» {page}-варақга қўшилди — «📐» билан жойига суринг.")

    def _pick_field(self, firm: Path, kind: str, question: str) -> int | None:
        fields = self._c.fields(firm, kind)
        if not fields:
            self._warn("Бу бланкада ҳали матн йўқ — «➕ Матн» билан қўшинг.")
            return None
        labels = [f"{i + 1}. {f.label()} ({f.page}-варақ)"
                  for i, f in enumerate(fields)]
        picked, ok = QInputDialog.getItem(self, "ТРУДАВОЙ", question, labels,
                                          0, False)
        if not ok:
            return None
        return labels.index(picked)

    def _remove_field(self) -> None:
        firm = self._firm_now()
        if firm is None:
            return
        kind = self._pick_kind("Қайси бланкадан?")
        if kind is None:
            return
        index = self._pick_field(firm, kind, "Қайси матн ўчирилсин?")
        if index is None:
            return
        self._c.remove_field(firm, kind, index)
        self._show_state()
        self._status.setText("✅ Матн ўчирилди.")

    def _style_field(self) -> None:
        firm = self._firm_now()
        if firm is None:
            return
        kind = self._pick_kind("Қайси бланкада?")
        if kind is None:
            return
        index = self._pick_field(firm, kind, "Қайси матн?")
        if index is None:
            return
        colour = QColorDialog.getColor(parent=self, title="Матн ранги")
        if not colour.isValid():
            return
        weight, ok = QInputDialog.getItem(
            self, "Қалинлиги", "Матн қалинлиги:",
            ["Юпқа (оддий)", "Қалин (жирний)"], 0, False)
        if not ok:
            return
        face, ok = QInputDialog.getItem(
            self, "Шрифт", "Шрифт тури:",
            ["Times New Roman (сериф)", "Arial / Calibri (сансериф)"], 0, False)
        if not ok:
            return
        self._c.restyle_field(
            firm, kind, index,
            colour=(colour.redF(), colour.greenF(), colour.blueF()),
            bold=weight.startswith("Қалин"), serif=face.startswith("Times"))
        self._status.setText("✅ Матннинг ранги, қалинлиги ва шрифти сақланди.")

    # ----------------------------------------------------------- arrange
    def _arrange(self, kind: str) -> None:
        firm = self._firm_now()
        if firm is None:
            return
        import fitz

        from src.ui.widgets.layout_editor import Item
        from src.ui.widgets.multipage_layout_editor import MultiPageLayoutEditor

        blank = self._c.blank(firm, kind)
        if blank is None:
            self._warn("Бу фирмада бундай бланка йўқ — аввал PDF ини юкланг.")
            return
        fields = self._c.fields(firm, kind)
        if not fields:
            self._warn("Бу бланкада ҳали матн йўқ — «➕ Матн» билан қўшинг.")
            return
        try:
            pages = []
            with fitz.open(str(blank)) as doc:
                for page in doc:
                    pages.append(page.get_pixmap(dpi=100).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        items_by_page: dict[int, list[Item]] = {}
        for index, item in enumerate(fields):
            if item.page > len(pages):
                continue
            items_by_page.setdefault(item.page, []).append(
                Item(key=f"{item.key}#{index}", label=item.label(),
                     sample=item.sample(), x=item.x, baseline=item.baseline,
                     size=item.size, colour=item.colour,
                     font_family=("Times New Roman" if item.serif
                                  else "Arial")))
        if not items_by_page:
            self._warn("Матнлар бу бланкада йўқ варақларга қўйилган.")
            return
        tag = "ТД" if kind == "td" else "УВ"
        dialog = MultiPageLayoutEditor(pages, items_by_page,
                                       title=f"ТРУД {tag}", parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.move_fields(firm, kind, dialog.result().items)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(f"✅ {tag} матнларининг жойи сақланди.")

    # ---------------------------------------------------------- printing
    def _generate(self) -> None:
        firm = self._firm_now()
        if firm is None:
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
                firm=firm, passport=read_passport, patent=read_patent,
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
