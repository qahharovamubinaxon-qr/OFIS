"""УЗБ СПРАВКАЛАР — the four certificates one worker's agency asks for.

The office drops his passport, the program reads his rows and digs his ПИНФЛ
out of the strip at the foot of the page, and every value lands in a box the
office can type over before anything is printed. Then it picks the firm — its
seal is what goes on all four — ticks the certificates it needs, and presses
once.

What comes out is four PDFs, each with its OWN four-digit code at the foot and
a QR beside it that opens that certificate and no other.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
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
from src.controllers.uzbspravka_controller import UzbSpravkaController
from src.pdf.uzbspravka_renderer import UzbData
from src.pdf.uzbspravka_spec import SEAL_KEY, SEAL_LABEL
from src.services.uzbspravka_service import SheetNumbers
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

_QR_LABEL = "▦ QR (код ортидаги ҳавола)"


class UzbSpravkaView(QWidget):
    def __init__(self, controller: UzbSpravkaController) -> None:
        super().__init__()
        self._c = controller
        self._numbers: dict[int, SheetNumbers] = controller.new_numbers()

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

        title = QLabel("УЗБ СПРАВКАЛАР — 4 справка")
        title.setObjectName("viewTitle")
        root.addWidget(title)
        note = QLabel(
            "Паспортни ташланг → «Ўқиш» → маълумотни текширинг → фирмани "
            "танланг → «Тайёрлаш». Ҳар справка ўз 4 хонали коди билан "
            "чиқади: битта варақ ёлғиз кетса, фақат ўзини очади.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8a94a3;")
        root.addWidget(note)

        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт (маълумот бети)")
        docs.addWidget(self._passport)
        read = QPushButton("📖 Ўқиш")
        read.setToolTip("Паспортнинг қаторлари ва пастки стрипдаги ПИНФЛ")
        read.clicked.connect(self._read)
        docs.addWidget(read)
        docs.addStretch(1)
        root.addLayout(docs)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        root.addLayout(form)

        self._surname = self._box(form, 0, 0, "Фамилия:", "ЭРГАШЕВ")
        self._name = self._box(form, 0, 2, "Исм:", "УМИДЖОН")
        self._patronymic = self._box(form, 1, 0, "Отчество:", "ШУХРАТ УГЛИ")
        self._latin = self._box(form, 1, 2, "Лотинча ФИО:",
                                "ERGASHEV UMIDJON SHUKHRAT UGLI")
        self._passport_no = self._box(form, 2, 0, "Паспорт:", "FA3445084")
        self._pinfl = self._box(form, 2, 2, "ПИНФЛ:", "50210025720042")
        self._pinfl.setToolTip("Паспортнинг пастки стрипидан ўқилади — "
                               "ўқилмаса ўзингиз ёзасиз")

        form.addWidget(QLabel("Туғилган сана:"), 3, 0)
        self._born = QDateEdit(QDate(2000, 1, 1))
        self._born.setCalendarPopup(True)
        self._born.setDisplayFormat("dd.MM.yyyy")
        form.addWidget(self._born, 3, 1)

        form.addWidget(QLabel("Фирма:"), 3, 2)
        self._firm = QComboBox()
        self._firm.setToolTip("Ишчи қайси фирмада ишласа — тўрттала "
                              "справкага ўшанинг печати тушади")
        form.addWidget(self._firm, 3, 3)
        self._show_firms()

        # The office's own date. Everything the certificate says about WHEN
        # follows this box and not the computer's clock: the top-right stamp,
        # «Дата создания» and «Дата выдачи» on all four.
        form.addWidget(QLabel("Справка санаси:"), 4, 0)
        self._made = QDateEdit(QDate.currentDate())
        self._made.setCalendarPopup(True)
        self._made.setDisplayFormat("dd.MM.yyyy")
        self._made.setToolTip("Справкалар шу числода чиққан бўлади — "
                              "тепадаги сана, «создания» ва «выдачи»")
        form.addWidget(self._made, 4, 1)

        sheets_row = QHBoxLayout()
        sheets_row.addWidget(QLabel("Справкалар:"))
        self._ticks: dict[int, QCheckBox] = {}
        names = self._c.sheet_names()
        short = self._c.sheet_short()
        for sheet in self._c.sheets():
            tick = QCheckBox(f"{sheet} · {short.get(sheet, '')}".strip(" ·"))
            tick.setChecked(True)
            tick.setToolTip(names.get(sheet, ""))
            self._ticks[sheet] = tick
            sheets_row.addWidget(tick)
        self._qr = QCheckBox(_QR_LABEL)
        self._qr.setChecked(self._c.can_make_qr())
        self._qr.setEnabled(self._c.can_make_qr())
        self._qr.setToolTip(
            "imgbb ва QRIXTOOLS калитлари Созламаларда бўлса ишлайди"
            if self._c.can_make_qr() else
            "Калитлар йўқ — Созламаларда «КРКОД РЕГ» ва «QRIXTOOLS»")
        sheets_row.addSpacing(16)
        sheets_row.addWidget(self._qr)
        sheets_row.addStretch(1)
        root.addLayout(sheets_row)

        tools = QHBoxLayout()
        for label, tip, slot in (
            ("📄 Бланкалар", "Ҳар справканинг ўз скани — бир марта юкланади",
             self._blanks),
            ("⬤ Печатлар", "Ҳар фирманинг ўз печати, ўз номи билан",
             self._seals),
            ("🔢 Рақамлар", "Код, № охири ва заявка — ҳар справка ўзиники",
             self._edit_numbers),
            ("📐 Созлаш", "Матнларни суриш, катта-кичик қилиш, ранг ва шрифт",
             self._arrange),
        ):
            button = QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            tools.addWidget(button)
        tools.addStretch(1)
        root.addLayout(tools)

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
        # the codes are read off this line and typed into the site, so it
        # must be selectable
        self._status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._status)
        root.addStretch(1)

    @staticmethod
    def _box(form: QGridLayout, row: int, column: int, label: str,
             hint: str) -> QLineEdit:
        form.addWidget(QLabel(label), row, column)
        edit = QLineEdit()
        edit.setPlaceholderText(hint)
        form.addWidget(edit, row, column + 1)
        return edit

    # --------------------------------------------------------------- state
    def _show_firms(self) -> None:
        """The firms whose seals the office has uploaded, and only those."""
        kept = self._firm.currentText()
        self._firm.clear()
        self._firm.addItems(sorted(self._c.seals()))
        if kept:
            self._firm.setCurrentText(kept)

    def _data(self) -> UzbData:
        """What is in the boxes — never what was read, always what is shown."""
        return UzbData(
            surname=self._surname.text().strip(),
            name=self._name.text().strip(),
            patronymic=self._patronymic.text().strip(),
            latin_name=self._latin.text().strip(),
            birth_date=self._born.date().toPython(),
            passport=self._passport_no.text().strip(),
            pinfl=self._pinfl.text().strip(),
            firm=self._firm.currentText().strip(),
            made_at=self._when())

    def _when(self) -> datetime:
        """The date the office chose, at the hour it is printing.

        The certificates print a time as well as a day, and the office picks
        the DAY — a справка dated last Tuesday is still made now, so the
        clock supplies the hour and the box supplies everything else.
        """
        return datetime.combine(self._made.date().toPython(),
                                datetime.now().time().replace(microsecond=0))

    def _wanted(self) -> tuple[int, ...]:
        return tuple(s for s, tick in self._ticks.items() if tick.isChecked())

    # ------------------------------------------------------------- reading
    def _read(self) -> None:
        if self._passport.path is None:
            self._warn("Паспортнинг маълумот бетини ташланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        image = Path(self._passport.path).read_bytes()
        firm = self._firm.currentText().strip()
        self._run.setEnabled(False)
        self._progress.start("Паспорт ва пастки стрип ўқиляпти…")
        run_async(lambda: self._c.read_passport(image, firm=firm),
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, data: UzbData) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._surname.setText(data.surname)
        self._name.setText(data.name)
        self._patronymic.setText(data.patronymic)
        self._latin.setText(data.latin_name)
        self._passport_no.setText(data.passport)
        self._pinfl.setText(data.pinfl)
        if data.birth_date:
            self._born.setDate(QDate(data.birth_date.year,
                                     data.birth_date.month,
                                     data.birth_date.day))
        self._status.setText(
            "✅ Ўқилди — текширинг ва «Тайёрлаш»." if data.pinfl else
            "⚠️ ПИНФЛ ўқилмади (стрип хира ёки кесилган) — паспортдан "
            "кўчириб ёзинг. Қолгани ўқилди.")

    # -------------------------------------------------------------- blanks
    def _blanks(self) -> None:
        have = self._c.blanks()
        names = self._c.sheet_names()
        lines = "\n".join(
            f"  {s}-справка ({names[s]}): "
            f"{'✅ ' + have[s].name if s in have else '— йўқ'}"
            for s in self._c.sheets())
        box = QMessageBox(self)
        box.setWindowTitle("Бланкалар")
        box.setText(f"{lines}\n\nҚайси справканинг бланкасини юкласиз?")
        buttons = {}
        for sheet in self._c.sheets():
            buttons[box.addButton(f"{sheet}-справка",
                                  QMessageBox.ButtonRole.ActionRole)] = sheet
        clear = box.addButton("🗑 Ҳаммасини тозалаш",
                              QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Ёпиш", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        picked = box.clickedButton()
        if picked is clear:
            for sheet in self._c.sheets():
                self._c.clear_blank(sheet)
            self._status.setText("✅ Бланкалар тозаланди.")
            return
        sheet = buttons.get(picked)
        if sheet is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, f"{sheet}-справка бланкаси", "",
            "Бланка (*.pdf *.png *.jpg *.jpeg)")
        if not path:
            return
        try:
            self._c.set_blank(sheet, Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(f"✅ {sheet}-справка бланкаси юкланди.")

    # --------------------------------------------------------------- seals
    def _seals(self) -> None:
        have = self._c.seals()
        lines = "\n".join(f"  ⬤ {firm}" for firm in sorted(have)) \
            or "  — ҳали печать юкланмаган"
        box = QMessageBox(self)
        box.setWindowTitle("Фирма печатлари")
        box.setText(f"Печатлар:\n{lines}\n\nНима қиламиз?")
        add = box.addButton("➕ Печать қўшиш",
                            QMessageBox.ButtonRole.ActionRole)
        drop = box.addButton("🗑 Ўчириш",
                             QMessageBox.ButtonRole.DestructiveRole) \
            if have else None
        box.addButton("Ёпиш", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        picked = box.clickedButton()
        if picked is add:
            self._add_seal()
        elif drop is not None and picked is drop:
            self._drop_seal(sorted(have))

    def _add_seal(self) -> None:
        firm, said = QInputDialog.getText(
            self, "Фирма", "Фирма номи (печат ўша ном билан сақланади):",
            text=self._firm.currentText())
        if not said or not firm.strip():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, f"«{firm.strip()}» печати (шаффоф PNG яхши)", "",
            "Расм (*.png *.jpg *.jpeg)")
        if not path:
            return
        try:
            self._c.add_seal(firm.strip(), Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._show_firms()
        self._firm.setCurrentText(firm.strip())
        self._status.setText(f"✅ «{firm.strip()}» печати юкланди — жойини "
                             "«📐 Созлаш» да белгиланг.")

    def _drop_seal(self, firms: list[str]) -> None:
        firm, said = QInputDialog.getItem(
            self, "Печатни ўчириш", "Қайси фирма?", firms, 0, False)
        if not said or not firm:
            return
        self._c.remove_seal(firm)
        self._show_firms()
        self._status.setText(f"✅ «{firm}» печати ўчирилди.")

    # ------------------------------------------------------------- numbers
    def _edit_numbers(self) -> None:
        """Each certificate's own three numbers, offered and editable."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Рақамлар — ҳар справка ўзиники")
        grid = QGridLayout(dialog)
        for column, head in enumerate(("Справка", "Код (4 хона)",
                                       "№ охири", "Заявка")):
            grid.addWidget(QLabel(f"<b>{head}</b>"), 0, column)
        boxes: dict[int, tuple[QLineEdit, QLineEdit, QLineEdit]] = {}
        for row, sheet in enumerate(self._c.sheets(), start=1):
            own = self._numbers.get(sheet) or SheetNumbers()
            grid.addWidget(QLabel(f"{sheet}"), row, 0)
            made = (QLineEdit(own.code), QLineEdit(own.number_tail),
                    QLineEdit(own.request_no))
            for column, edit in enumerate(made, start=1):
                grid.addWidget(edit, row, column)
            boxes[sheet] = made
        again = QPushButton("🎲 Янгиларини олиш")

        def refresh() -> None:
            fresh = self._c.new_numbers()
            for sheet, (code, tail, request) in boxes.items():
                own = fresh[sheet]
                code.setText(own.code)
                tail.setText(own.number_tail)
                request.setText(own.request_no)

        again.clicked.connect(refresh)
        grid.addWidget(again, len(boxes) + 1, 0, 1, 2)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        grid.addWidget(buttons, len(boxes) + 1, 2, 1, 2)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._numbers = {
            sheet: SheetNumbers(code=code.text().strip(),
                                number_tail=tail.text().strip(),
                                request_no=request.text().strip())
            for sheet, (code, tail, request) in boxes.items()}
        self._status.setText("✅ Рақамлар сақланди (шу ишчи учун).")

    # ------------------------------------------------------------- arrange
    def _arrange(self) -> None:
        """All four sheets in one window — each remembers its own places."""
        import fitz

        from src.pdf.uzbspravka_renderer import QR_KEY, render
        from src.ui.widgets.field_editor import FieldEditor

        sheets = self._c.sheets()
        blanks = self._c.blanks()
        sample = UzbData(
            surname="ЭРГАШЕВ", name="УМИДЖОН", patronymic="ШУХРАТ УГЛИ",
            latin_name="ERGASHEV UMIDJON SHUKHRAT UGLI",
            birth_date=date(2002, 10, 2), passport="FA3445084",
            pinfl="50210025720042", number_tail="9330-6055", code="1548",
            request_no="170387888", made_at=datetime.now())
        try:
            pages = []
            for sheet in sheets:
                with fitz.open("pdf", render(sample, sheet,
                                             blanks.get(sheet))) as doc:
                    pages.append(doc[0].get_pixmap(dpi=52).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        layout = self._c.layout()
        catalogue, samples, fields = to_fields(sheets, layout)

        pictures: dict[str, bytes] = {}
        seal = self._c.seals().get(self._firm.currentText().strip())
        for sheet in sheets:
            if seal is not None:
                pictures[f"{sheet}:{SEAL_KEY}"] = seal.read_bytes()
            pictures[f"{sheet}:{QR_KEY}"] = _sample_qr()

        dialog = FieldEditor(pages, fields, title="УЗБ справкалар",
                             parent=self, catalogue=catalogue, samples=samples,
                             frozen=set(catalogue), images=pictures)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._c.save_layout(to_layout(dialog.fields(), samples))
        self._status.setText("✅ Жойлар сақланди — ҳар справка ўзиникини "
                             "эслаб қолди.")

    # ------------------------------------------------------------ printing
    def _generate(self) -> None:
        if not self._surname.text().strip():
            self._warn("Фамилия бўш — паспортни ўқитинг ёки ўзингиз ёзинг.")
            return
        if not self._firm.currentText().strip():
            self._warn("Фирма танланмаган — «⬤ Печатлар» орқали қўшинг.")
            return
        wanted = self._wanted()
        if not wanted:
            self._warn("Ҳеч бўлмаса битта справкани белгиланг.")
            return
        data = self._data()
        numbers = dict(self._numbers)
        with_qr = self._qr.isChecked()

        self._run.setEnabled(False)
        self._progress.start(
            f"{len(wanted)} та справка тайёрланаяпти…"
            + (" QR учун ҳар бири юкланади." if with_qr else ""))
        run_async(lambda: self._c.generate(data, wanted, numbers=numbers,
                                           with_qr=with_qr),
                  on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        lines = "  ·  ".join(f"{sheet}: код {result.codes[sheet]}"
                             for sheet in sorted(result.pdfs))
        self._status.setText(
            f"✅ {len(result.pdfs)} та справка тайёр — «{result.firm}»\n"
            f"{lines}")
        # a fresh worker must not carry the last one's codes
        self._numbers = self._c.new_numbers()
        from src.ui.widgets.save_to import ask_save_dir

        ask_save_dir(self, [result.pdfs[s] for s in sorted(result.pdfs)])

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.services.uzbspravka_service import SECTION
        from src.ui.views.settings_view import _open_folder

        made = paths.output_dir() / SECTION
        made.mkdir(parents=True, exist_ok=True)
        _open_folder(made)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        self._passport.clear()


def _sample_qr() -> bytes:
    """A QR that stands in while the office is placing it — never printed."""
    from src.services.qrixtools import qr_png

    return qr_png("https://qrixtools.com/s/XXXXXX", size=6)


# ---------------------------------------------------------- the arranger
# The four sheets go into ONE editor window, and the editor knows a text by
# its key alone — while sheets 1, 2 and 3 carry the same names, because they
# are the same sheet with different words. So every key goes in wearing its
# sheet: «4:pinfl» is not «1:pinfl», and dragging one leaves the other where
# the office put it. These two are the way in and the way back out.
def to_fields(sheets, layout: dict):
    """(catalogue, samples, fields) for the editor, sheet by sheet."""
    from src.pdf.trud8_fields import Field
    from src.pdf.uzbspravka_renderer import placed, placed_images

    catalogue: dict[str, str] = {}
    samples: dict[str, str] = {}
    fields: list = []
    for sheet in sheets:
        for key, slot in placed(sheet, layout).items():
            tag = f"{sheet}:{key}"
            catalogue[tag] = f"{sheet}-справка · {slot.label or key}"
            samples[tag] = slot.sample or key
            fields.append(Field(
                key=tag, page=sheet, x=slot.x, baseline=slot.baseline,
                size=slot.size, colour=tuple(slot.colour)[:3],
                bold=slot.bold, font=slot.family))
        for key, (x, bottom, height) in placed_images(sheet, layout).items():
            tag = f"{sheet}:{key}"
            label = SEAL_LABEL if key == SEAL_KEY else _QR_LABEL
            catalogue[tag] = f"{sheet}-справка · {label}"
            samples[tag] = label
            fields.append(Field(key=tag, page=sheet, x=x, baseline=bottom,
                                size=height, colour=(0.0, 0.0, 0.0),
                                bold=False, font="Arial"))
    return catalogue, samples, fields


def to_layout(fields, samples: dict[str, str]) -> dict:
    """What the editor left, in the shape the renderer reads back."""
    from src.pdf.uzbspravka_renderer import QR_KEY

    made: dict[str, dict] = {"fields": {}, "styles": {}, "images": {}}
    extra: list[dict] = []
    for field in fields:
        sheet, _, key = field.key.partition(":")
        place = [round(field.x, 5), round(field.baseline, 5),
                 round(field.size, 5)]
        if not key:                        # a text the office added itself
            extra.append({"text": samples.get(field.key, "матн"),
                          "sheet": field.page, "x": place[0],
                          "baseline": place[1], "size": place[2],
                          "font": field.font, "bold": field.bold,
                          "colour": list(field.colour)})
        elif key in (SEAL_KEY, QR_KEY):
            made["images"].setdefault(sheet, {})[key] = place
        else:
            made["fields"].setdefault(sheet, {})[key] = place
            made["styles"].setdefault(sheet, {})[key] = {
                "font": field.font, "bold": field.bold,
                "colour": list(field.colour), "size": place[2]}
    return {**made, "extra": extra}
