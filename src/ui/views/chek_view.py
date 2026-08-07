"""ЧЕК screen — премия чеки: патент расми + число/соат + сумма → PDF.

Flow: drop the patent → AI fills Фамилия/Исм/Отчество/ИНН (all four stay
editable — the operator reviews before generating), pick date + h:m:s, type
the amount and the card's last 4 digits, choose a template, RUN. The PDF is
offered for saving with the Desktop as the default folder, named
"Документ-YYYY-MM-DD-HH-MM-SS.pdf" from the ENTERED date and time.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.threading import run_async
from src.controllers.chek_controller import ChekController
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


def _desktop() -> Path:
    for cand in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if cand.exists():
            return cand
    return Path.home()


class ChekView(QWidget):
    def __init__(self, controller: ChekController) -> None:
        super().__init__()
        self._c = controller
        self._last_pdf: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ЧЕК — премия чеки")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        self._dz = DropZone("🧾", "Ишчининг ПАТЕНТИ расми")
        self._dz.changed.connect(self._on_drop)
        root.addWidget(self._dz, stretch=1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self._fam = self._line(grid, 0, 0, "Фамилия:")
        self._ism = self._line(grid, 0, 2, "Исм:")
        self._otch = self._line(grid, 1, 0, "Отчество:")
        self._inn = self._line(grid, 1, 2, "ИНН (патентдан):")
        self._inn.setMaxLength(12)
        root.addLayout(grid)

        row = QHBoxLayout()
        row.addWidget(QLabel("Число:"))
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(self._date)
        row.addWidget(QLabel("Соат:"))
        self._time = QTimeEdit()
        self._time.setDisplayFormat("HH:mm:ss")
        self._time.setTime(QTime.currentTime())
        row.addWidget(self._time)
        row.addWidget(QLabel("Сумма (₽):"))
        self._summa = QLineEdit()
        self._summa.setPlaceholderText("15000,50")
        self._summa.setFixedWidth(120)
        row.addWidget(self._summa)
        row.addWidget(QLabel("Карта охирги 4:"))
        self._card4 = QLineEdit()
        self._card4.setMaxLength(4)
        self._card4.setFixedWidth(70)
        row.addWidget(self._card4)
        row.addStretch(1)
        root.addLayout(row)

        # Neither of these two is ever generated: the authorisation code is
        # copied off the bank's confirmation, the company id is the office's.
        bank = QHBoxLayout()
        bank.addWidget(QLabel("Код авторизации:"))
        self._avtoriz = QLineEdit()
        self._avtoriz.setMaxLength(6)
        self._avtoriz.setFixedWidth(90)
        self._avtoriz.setPlaceholderText("357852")
        bank.addWidget(self._avtoriz)
        bank.addWidget(QLabel("Компания коди:"))
        self._company = QLineEdit()
        self._company.setFixedWidth(190)
        self._company.setPlaceholderText("бир марта ёзилади")
        self._company.setText(self._c.company_id())
        self._company.editingFinished.connect(
            lambda: self._c.set_company_id(self._company.text()))
        bank.addWidget(self._company)
        bank.addStretch(1)
        root.addLayout(bank)

        trow = QHBoxLayout()
        trow.addWidget(QLabel("Шаблон:"))
        self._tpl = QComboBox()
        self._reload_templates()
        trow.addWidget(self._tpl, stretch=1)
        add_btn = QPushButton("➕ Шаблон қўшиш")
        add_btn.clicked.connect(self._add_template)
        trow.addWidget(add_btn)
        drop_btn = QPushButton("🗑")
        drop_btn.setToolTip("Танланган шаблонни ўчириш — юкланган шаблон "
                            "шундан бошқа ҳеч қачон йўқолмайди")
        drop_btn.clicked.connect(self._remove_template)
        trow.addWidget(drop_btn)
        arrange = QPushButton("📐 Матнларни жойлаш")
        arrange.setToolTip("Бланка ва унга ёзиладиган маълумотлар экранга "
                           "чиқади — сичқонча билан суриб, катта-кичик қилиб "
                           "жойига қўйинг. Шу шаблон учун сақланиб қолади.")
        arrange.clicked.connect(self._arrange)
        trow.addWidget(arrange)
        trow.addStretch(1)
        root.addLayout(trow)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (ЧЕК PDF)")
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

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel(
            "Патент расмини ташланг — Ф.И.О. ва ИНН ўзи ўқилади (текшириб "
            "тўғрилаш мумкин). Число, соат, сумма ва карта рақамининг охирги "
            "4 тасини киритиб RUN босинг — PDF Рабочий столга сақланади.\n"
            "Код авторизации банк квитанциясидан кўчирилади, компания коди "
            "бир марта ёзилади — иккисини ҳам программа ўйлаб чиқармайди.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

    @staticmethod
    def _line(grid: QGridLayout, r: int, c: int, label: str) -> QLineEdit:
        grid.addWidget(QLabel(label), r, c)
        edit = QLineEdit()
        grid.addWidget(edit, r, c + 1)
        return edit

    # ── patent OCR ───────────────────────────────────────────────────
    def _on_drop(self) -> None:
        if self._dz.path is None:
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        data = Path(self._dz.path).read_bytes()
        self._status.setText("⏳ Патент ўқилаяпти…")
        self._progress.start("Патентдан Ф.И.О. ва ИНН ўқилаяпти…")
        run_async(self._c.read_patent_fields, data,
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, f: dict[str, str]) -> None:
        self._progress.finish()
        self._fam.setText(f["fam"])
        self._ism.setText(f["ism"])
        self._otch.setText(f["otch"])
        self._inn.setText(f["inn"])
        missing = [n for n, v in (("Фамилия", f["fam"]), ("Исм", f["ism"]),
                                  ("ИНН", f["inn"])) if not v]
        self._status.setText(
            "✅ Патент ўқилди — маълумотларни текшириб RUN босинг."
            + (f"  ⚠️ Ўқилмади: {', '.join(missing)} — қўлда киритинг." if missing else ""))

    # ── generate ─────────────────────────────────────────────────────
    def _generate(self) -> None:
        fam, ism = self._fam.text().strip(), self._ism.text().strip()
        otch, inn = self._otch.text().strip(), self._inn.text().strip()
        card4 = "".join(c for c in self._card4.text() if c.isdigit())
        if not fam or not ism:
            self._warn("Фамилия ва Исм бўш бўлмасин (патентни ўқитинг ёки қўлда ёзинг).")
            return
        if len("".join(c for c in inn if c.isdigit())) != 12:
            self._warn("ИНН 12 та рақам бўлиши керак.")
            return
        if len(card4) != 4:
            self._warn("Карта рақамининг охирги 4 та рақамини киритинг.")
            return
        try:
            rub, kop = self._c.parse_amount(self._summa.text())
        except ValueError:
            self._warn("Суммани тўғри киритинг, масалан: 15000,50")
            return
        avtoriz = "".join(c for c in self._avtoriz.text() if c.isdigit())
        if len(avtoriz) != 6:
            self._warn("Код авторизацияни банк квитанциясидан кўчириб ёзинг "
                       "(6 та рақам). Программа уни ўзи ўйлаб чиқармайди.")
            return
        self._c.set_company_id(self._company.text())
        if not self._c.company_id():
            self._warn("Компания кодини бир марта ёзиб қўйинг — усиз чек "
                       "чиқарилмайди.")
            return
        q, t = self._date.date(), self._time.time()
        when = datetime(q.year(), q.month(), q.day(), t.hour(), t.minute(), t.second())
        tpl = self._tpl.currentData()
        # the phone has no picker: it prints on whatever the desktop last used
        self._c.set_default_template(Path(tpl) if tpl else None)
        try:
            pdf, name = self._c.generate(fam=fam, ism=ism, otch=otch, inn=inn,
                                         card4=card4, when=when, rub=rub, kop=kop,
                                         avtoriz=avtoriz,
                                         template=Path(tpl) if tpl else None)
        except Exception as e:  # noqa: BLE001 — show the operator, don't crash
            self._failed(e)
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Чекни сақлаш", str(_desktop() / name), "PDF (*.pdf)")
        if not target:
            self._status.setText("Сақлаш бекор қилинди.")
            return
        Path(target).write_bytes(pdf)
        self._last_pdf = Path(target)
        self._open.setEnabled(True)
        self._status.setText(f"✅ Чек тайёр: {target}")

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + message)
        QMessageBox.warning(self, "Xato", message)

    def _open_folder(self) -> None:
        if self._last_pdf is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_pdf.parent)))

    def _warn(self, message: str) -> None:
        self._status.setText("⚠️ " + message)
        QMessageBox.information(self, "Diqqat", message)

    def _reload_templates(self) -> None:
        self._tpl.clear()
        for p in self._c.templates():
            self._tpl.addItem(p.stem, str(p))

    def _remove_template(self) -> None:
        """The only thing that ever takes a blank off the list."""
        chosen = self._tpl.currentData()
        if not chosen:
            self._warn("Ўчириш учун шаблонни танланг.")
            return
        template = Path(chosen)
        if QMessageBox.question(
                self, "Шаблонни ўчириш",
                f"«{template.stem}» ўчирилсинми?\n\nЖойлаштирган матнлари "
                "ҳам ўчади.") != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_template(template)
        self._reload_templates()
        self._status.setText(f"✅ Шаблон ўчирилди: {template.stem}")

    def _add_template(self) -> None:
        src, _ = QFileDialog.getOpenFileName(
            self, "Янги чек шаблони (бўш бланка PDF)", str(_desktop()), "PDF (*.pdf)")
        if not src:
            return
        dest = self._c.add_template(Path(src))
        self._reload_templates()
        self._tpl.setCurrentIndex(self._tpl.findData(str(dest)))
        self._status.setText(f"✅ Шаблон қўшилди: {dest.name}")
        if QMessageBox.question(
                self, "Матнларни жойлаш",
                "Маълумотларни шу бланкага мослаб қўяйликми? "
                "(сичқонча билан суриб, катта-кичик қилиб — сақланиб қолади)"
        ) == QMessageBox.StandardButton.Yes:
            self._arrange()

    def _arrange(self) -> None:
        """Drag every printed value into place on THIS blank and keep it."""
        import fitz

        from src.pdf.chek_renderer import effective
        from src.pdf.chek_spec import SAMPLES, SCREEN_FONT
        from src.ui.widgets.layout_editor import Item, LayoutEditor

        tpl = self._tpl.currentData()
        if not tpl:
            self._status.setText("⚠️ Аввал шаблонни танланг.")
            return
        template = Path(tpl)
        # arranging a blank is a statement that this is the office's blank
        self._c.set_default_template(template)
        try:
            with fitz.open(str(template)) as doc:
                page = doc[0]
                width, height = page.rect.width, page.rect.height
                fields = effective(page, self._c.layout(template))
                png = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6)).tobytes("png")
        except Exception as exc:                  # noqa: BLE001
            self._status.setText(f"❌ Бланка очилмади: {exc}")
            return

        items = []
        for key, label, sample in SAMPLES:
            spot = fields.get(key)
            if spot is None:
                continue
            x0, _y0, _x1, y1 = spot["rect"]
            items.append(Item(key=key, label=label, sample=sample,
                              x=x0 / width, baseline=(y1 - 2.2) / height,
                              size=spot["size"] / height,
                              font_family=SCREEN_FONT))
        dialog = LayoutEditor(png, items, title="ЧЕК — матнларни жойлаш",
                              parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._c.save_layout(template, {"fields": dialog.result().items})
        self._status.setText(
            f"✅ «{template.stem}» шаблонининг матн жойлари сақланди — "
            "бу шаблонга босиладиган ҳар бир чек шу жойларга тушади.")

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        self._dz.clear()
        for w in (self._fam, self._ism, self._otch, self._inn, self._summa,
                  self._card4, self._avtoriz):
            w.clear()  # the company id stays — it belongs to the office
        self._last_pdf = None
        self._open.setEnabled(False)
