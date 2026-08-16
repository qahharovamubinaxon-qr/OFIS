"""ТРУД ППУ screen — three sheets from the worker's own folder.

Drop the трудовой договор, the уведомление, both sides of the patent and the
worker's photograph. The program reads them, fills the form, and the operator
checks it before printing — every field stays editable, because a firm name or
a contract date that is wrong on a filed package is not a small thing.

Sheet 1 is printed on the ППУ front blank the ППУ section already holds, so it
comes out identical to the ППУ's own front sheet. Sheets 2 and 3 are printed on
the pair uploaded here. All three are saved to the desktop as pictures.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
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

from src.common.errors import OfisError
from src.common.threading import run_async
from src.controllers.trud_ppu_controller import TrudPpuController
from src.pdf.trud_ppu_renderer import case_number, plus_one_year
from src.ui.widgets.drop_zone import PDF_EXTS, DropZone
from src.ui.widgets.run_progress import RunProgress


def _desktop() -> Path:
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.exists():
            return candidate
    return Path.home()


class TrudPpuView(QWidget):
    def __init__(self, controller: TrudPpuController,
                 ppu_templates: Callable[[], list[Path]]) -> None:
        super().__init__()
        self._c = controller
        self._ppu_templates = ppu_templates
        self._last: Path | None = None

        # This screen carries five drop zones, fifteen boxes, two blank
        # pickers and a preview. Laid straight into the window they had
        # nowhere to go on the office's screen and Qt squeezed the rows into
        # each other until the labels were unreadable. It scrolls, like every
        # other screen this long does.
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

        title = QLabel("ТРУД ППУ — трудовой + уведомление + патент → 3 саҳифа")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        zones = QHBoxLayout()
        self._trud = DropZone("📄", "ТРУДОВОЙ (PDF)", extensions=PDF_EXTS)
        self._trud.changed.connect(self._on_contract)
        zones.addWidget(self._trud, stretch=1)
        self._uved = DropZone("📨", "УВЕДОМЛЕНИЯ (PDF)", extensions=PDF_EXTS)
        self._uved.changed.connect(self._on_uved)
        zones.addWidget(self._uved, stretch=1)
        self._patent_front = DropZone("🪪", "ПАТЕНТ — олд томони")
        self._patent_front.changed.connect(self._on_patent)
        zones.addWidget(self._patent_front, stretch=1)
        self._patent_back = DropZone("🔄", "ПАТЕНТ — орқа томони")
        self._patent_back.changed.connect(self._on_patent)
        zones.addWidget(self._patent_back, stretch=1)
        self._photo = DropZone("🖼️", "Ишчининг РАСМИ")
        zones.addWidget(self._photo, stretch=1)
        root.addLayout(zones)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self._surname = self._line(grid, 0, 0, "Фамилия:")
        self._name = self._line(grid, 0, 2, "Имя:")
        self._patronymic = self._line(grid, 1, 0, "Отчество:")
        self._birth = self._line(grid, 1, 2, "Дата рождения:")
        self._birth.setPlaceholderText("03.03.1977")
        self._gender = self._line(grid, 2, 0, "Пол:")
        self._gender.setPlaceholderText("Мужской")
        self._citizenship = self._line(grid, 2, 2, "Гражданство:")
        self._document = self._line(grid, 3, 0, "Паспорт (серия/номер):")
        self._document.setToolTip(
            "1-саҳифанинг пастидаги «Иностранный паспорт» — ППУ дагидек.")
        root.addLayout(grid)

        patent = QGridLayout()
        patent.setHorizontalSpacing(14)
        patent.setVerticalSpacing(8)
        self._series = self._line(patent, 0, 0, "① Патент серияси:")
        self._series.setPlaceholderText("77")
        self._series.textChanged.connect(self._recalc)
        self._number = self._line(patent, 0, 2, "① Патент номери:")
        self._number.setPlaceholderText("2400328451")
        self._number.textChanged.connect(self._recalc)
        self._issue = self._line(patent, 1, 0, "②⑤ Патент олинган:")
        self._issue.setPlaceholderText("18.07.2024")
        self._issue.textChanged.connect(self._recalc)
        self._valid_to = self._line(patent, 1, 2, "③ Тугайди:")
        self._valid_to.setPlaceholderText("18.07.2025")
        self._valid_to.setToolTip(
            "Олинган санадан роппа-роса бир йил кейин — ўзи ҳисобланади, "
            "керак бўлса тузатинг.")
        self._case = self._line(patent, 2, 0, "④ Номер дела:")
        self._case.setToolTip(
            "Патент номери ва серияси тескари, охирида ПАТ — ўзи ясалади.")
        self._contract = self._line(patent, 2, 2, "⑥ Трудовой санаси:")
        self._contract.setPlaceholderText("20.09.2024")
        self._firm = self._line(patent, 3, 0, "⑦ Фирма:")
        self._firm.setPlaceholderText("ООО “ЭКСПЕРТ”")
        patent.addWidget(self._firm, 3, 1, 1, 3)
        self._uved_number = self._line(patent, 4, 0, "⑧ Уведомление №:")
        self._uved_number.setPlaceholderText("4785796716")
        self._uved_fio = self._line(patent, 4, 2, "⑨ Уведомлениядаги Ф.И.О.:")
        self._uved_fio.setToolTip(
            "Бўш қолдирсангиз — юқоридаги Фамилия/Имя/Отчество ёзилади.")
        root.addLayout(patent)

        order = QLabel(
            "🗂 <b>Бланкалар тартиби</b> — «➕ Шаблон қўшиш» иккита файл сўрайди, "
            "шу тартибда:<br>"
            "<b>1-саҳифа</b> — ҳеч нима сўралмайди: <b>ППУ бўлимидаги ОЛД "
            "бланка</b> ишлатилади (ўнгдаги «ППУ бланкаси» рўйхати). Агар у "
            "юкланмаган бўлса — аввал ППУ бўлимида юкла.<br>"
            "<b>2-саҳифа</b> — биринчи сўралади: <b>патент бети</b>, кўндаланг "
            "(«2 ТРУД ППУ ШОБЛОН ПУСТОЙ.pdf»).<br>"
            "<b>3-саҳифа</b> — иккинчи сўралади: <b>уведомление бети</b>, тик "
            "(«ТРУД ППУ 3 ШАБЛОН ПУСТОЙ.pdf»).")
        order.setWordWrap(True)
        order.setStyleSheet("color:#8a94a3;")
        root.addWidget(order)

        templates = QHBoxLayout()
        templates.addWidget(QLabel("ППУ бланкаси (1-саҳифа):"))
        self._ppu_template = QComboBox()
        templates.addWidget(self._ppu_template, stretch=1)
        templates.addWidget(QLabel("ТРУД ППУ бланкаси (2–3):"))
        self._template = QComboBox()
        templates.addWidget(self._template, stretch=1)
        add = QPushButton("➕ Шаблон қўшиш")
        add.setToolTip("2- ва 3-саҳифанинг бўш бланкаси (PDF)")
        add.clicked.connect(self._add_template)
        templates.addWidget(add)
        root.addLayout(templates)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (ТРУД ППУ)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._generate)
        actions.addWidget(self._run)
        self._open = QPushButton("📂 Папкани очиш")
        self._open.setEnabled(False)
        self._open.clicked.connect(self._open_folder)
        actions.addWidget(self._open)
        actions.addStretch(1)
        root.addLayout(actions)

        self._progress = RunProgress()
        root.addWidget(self._progress)

        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(160)
        root.addWidget(self._preview, stretch=1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel(
            "Трудовой ва уведомлениядан фирма, сана, номер ва Ф.И.О., "
            "патентдан серия, номер ва олинган сана ўқилади. Тугаш санаси "
            "олинган + 1 йил, «Номер дела» тескари тартибда ўзи ясалади. "
            "Уч саҳифа расм ҳолида Рабочий столга сақланади.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

        self._reload_templates()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _line(grid: QGridLayout, row: int, col: int, label: str) -> QLineEdit:
        grid.addWidget(QLabel(label), row, col)
        edit = QLineEdit()
        grid.addWidget(edit, row, col + 1)
        return edit

    def reload_templates(self) -> None:
        """Re-read both blank lists — a blank may have been added elsewhere."""
        self._reload_templates()

    def _reload_templates(self) -> None:
        self._ppu_template.clear()
        for folder in self._ppu_templates():
            self._ppu_template.addItem(folder.name, str(folder))
        if not self._ppu_template.count():
            self._ppu_template.addItem("— ППУ бланкаси йўқ —", None)

        self._template.clear()
        for folder in self._c.templates():
            self._template.addItem(folder.name, str(folder))
        if not self._template.count():
            self._template.addItem("— бланка юкланмаган —", None)

    def _add_template(self) -> None:
        page2, _ = QFileDialog.getOpenFileName(
            self, "1/2 — 2-САҲИФА: патент бети, бўш (2 ТРУД ППУ ШОБЛОН ПУСТОЙ)",
            str(_desktop()), "PDF (*.pdf)")
        if not page2:
            return
        page3, _ = QFileDialog.getOpenFileName(
            self, "2/2 — 3-САҲИФА: уведомление бети, бўш (ТРУД ППУ 3 ШАБЛОН ПУСТОЙ)",
            str(_desktop()), "PDF (*.pdf)")
        if not page3:
            return
        name, ok = QInputDialog.getText(self, "Шаблон номи", "Ном:")
        if not ok or not name.strip():
            return
        try:
            dest = self._c.add_template(name, Path(page2), Path(page3))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload_templates()
        self._template.setCurrentIndex(self._template.findData(str(dest)))
        self._status.setText(f"✅ Шаблон қўшилди: {dest.name}")

    def _recalc(self) -> None:
        """Keep the two values the office derives rather than reads in step."""
        issued = self._c.parse_date(self._issue.text())
        runs_to = plus_one_year(issued)
        if runs_to is not None:
            self._valid_to.setText(runs_to.strftime("%d.%m.%Y"))
        self._case.setText(case_number(self._series.text(), self._number.text()))

    def _need_ai(self) -> bool:
        if self._c.ai_available():
            return True
        self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
        return False

    # ----------------------------------------------------------- readers
    def _on_contract(self) -> None:
        if self._trud.path is None or not self._need_ai():
            return
        data = Path(self._trud.path).read_bytes()
        self._status.setText("⏳ Трудовой договор ўқилаяпти…")
        self._progress.start("Трудовойдан маълумот олинаяпти…")
        run_async(self._c.read_contract, data,
                  on_success=self._filled, on_error=self._failed)

    def _on_uved(self) -> None:
        if self._uved.path is None or not self._need_ai():
            return
        data = Path(self._uved.path).read_bytes()
        self._status.setText("⏳ Уведомление ўқилаяпти…")
        self._progress.start("Уведомлениядан номер олинаяпти…")
        run_async(self._c.read_uved, data,
                  on_success=self._filled, on_error=self._failed)

    def _on_patent(self) -> None:
        if self._patent_front.path is None or not self._need_ai():
            return
        front = Path(self._patent_front.path).read_bytes()
        back = (Path(self._patent_back.path).read_bytes()
                if self._patent_back.path is not None else None)
        self._status.setText("⏳ Патент ўқилаяпти…")
        self._progress.start("Патентдан серия ва сана олинаяпти…")
        run_async(lambda: self._c.read_patent(front, back),
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, fields: dict[str, str]) -> None:
        """Put whatever a reader found into the form, leaving the rest alone.

        The three readers each know part of the worker, and they run in whatever
        order the operator drops the files. So a reader only ever fills a field
        it actually found — it never blanks one another reader already filled.
        """
        self._progress.finish()
        for edit, key in (
                (self._surname, "surname"), (self._name, "name"),
                (self._patronymic, "patronymic"), (self._birth, "birth_date"),
                (self._gender, "gender"), (self._citizenship, "citizenship"),
                (self._document, "document"),
                (self._series, "patent_series"), (self._number, "patent_number"),
                (self._issue, "patent_issue"), (self._contract, "contract_date"),
                (self._firm, "firm"), (self._uved_number, "uved_number"),
                (self._uved_fio, "uved_fio")):
            if fields.get(key):
                edit.setText(fields[key])

        # The patent as the трудовой and the уведомление report it. The office
        # very often has those two and not the patent card, and both name the
        # patent — so rather than leave the boxes blank they are filled from
        # there. Only boxes STILL EMPTY are touched: a scanned patent card is
        # the patent itself and always outranks a mention of it, whichever
        # order the files happen to be dropped in.
        borrowed: list[str] = []
        for edit, key, said in ((self._series, "weak_patent_series", "серия"),
                                (self._number, "weak_patent_number", "номер"),
                                (self._issue, "weak_patent_issued",
                                 "олинган сана")):
            if fields.get(key) and not edit.text().strip():
                edit.setText(fields[key])
                borrowed.append(said)

        self._recalc()
        missing = [t for t, k in (("патент серияси", "patent_series"),
                                  ("патент номери", "patent_number"),
                                  ("олинган сана", "patent_issue"),
                                  ("фирма", "firm"),
                                  ("трудовой санаси", "contract_date"),
                                  ("уведомление номери", "uved_number"))
                   if k in fields and not fields.get(k)]
        self._status.setText(
            "✅ Ўқилди — текшириб RUN босинг."
            + (f"  🔎 Патент юкланмади — {', '.join(borrowed)} трудовой/"
               "уведомлениядан олинди, текширинг." if borrowed else "")
            + (f"  ⚠️ Ўқилмади: {', '.join(missing)} — қўлда киритинг."
               if missing else ""))

    # ----------------------------------------------------------- printing
    def _generate(self) -> None:
        photo = None
        if self._photo.path is not None:
            photo = Path(self._photo.path).read_bytes()
        ppu_template = self._ppu_template.currentData()
        template = self._template.currentData()
        try:
            result = self._c.generate(
                surname=self._surname.text(), name=self._name.text(),
                patronymic=self._patronymic.text(),
                birth_date=self._c.parse_date(self._birth.text()),
                gender=self._gender.text(),
                citizenship=self._citizenship.text(),
                document=self._document.text(),
                patent_series=self._series.text(),
                patent_number=self._number.text(),
                patent_issue=self._c.parse_date(self._issue.text()),
                patent_to=self._c.parse_date(self._valid_to.text()),
                contract_date=self._c.parse_date(self._contract.text()),
                firm=self._firm.text(),
                uved_number=self._uved_number.text(),
                uved_fio=self._uved_fio.text(),
                photo=photo,
                ppu_template=Path(ppu_template) if ppu_template else None,
                template=Path(template) if template else None)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        self._last = result.saved[0] if result.saved else None
        self._open.setEnabled(bool(result.saved))
        if result.pages:
            pix = QPixmap.fromImage(QImage.fromData(result.pages[1], "PNG"))
            self._preview.setPixmap(pix.scaledToHeight(
                max(160, self._preview.height()),
                Qt.TransformationMode.SmoothTransformation))
        warning = ("\n⚠️ Расм юкланмади — 1-саҳифа расмсиз чиқди."
                   if self._photo.path is None else "")
        names = ", ".join(p.name for p in result.saved)
        runs_to = (f" — {result.valid_to:%d.%m.%Y}" if result.valid_to else "")
        self._status.setText(
            f"✅ Рабочий столга сақланди: {names}\n"
            f"{result.patent}{runs_to} · {result.case_number} · {result.firm}"
            + warning)

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + message)
        QMessageBox.warning(self, "Xato", message)

    def _open_folder(self) -> None:
        if self._last is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last.parent)))

    def _warn(self, message: str) -> None:
        self._status.setText("⚠️ " + message)
        QMessageBox.information(self, "Diqqat", message)

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        """A new worker — the blanks and the templates stay."""
        for zone in (self._trud, self._uved, self._patent_front,
                     self._patent_back, self._photo):
            zone.clear()
        for edit in (self._surname, self._name, self._patronymic, self._birth,
                     self._gender, self._citizenship, self._document,
                     self._series, self._number, self._issue, self._valid_to,
                     self._case, self._contract, self._firm,
                     self._uved_number, self._uved_fio):
            edit.clear()
        self._preview.clear()
        self._last = None
        self._open.setEnabled(False)
