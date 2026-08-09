"""УНИВЕРСАЛ — one section for every form the office will ever upload.

The office said why it wanted this plainly: it does not want a new section
written for each new paper. So here it uploads the empty form, drags the
texts where they belong, names it and keeps it. From then on the form is in
the list, and filling it is: pick it, drop a passport, check what was read,
press Тайёрлаш.

The boxes on screen follow the FORM, not the program. A form that prints
nothing but a name shows a name; one that wants six series and numbers shows
six. That is what keeps this from becoming a wall of empty fields.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QGroupBox,
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
from src.controllers.universal_controller import UniversalController
from src.pdf.universal_fields import (
    DOC_SLOTS,
    SIGNATURE,
    STAMP,
    UniversalData,
)
from src.services.universal_service import UniversalResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

#: Which catalogue keys a plain text box fills.
_BOXES: tuple[tuple[str, str, str], ...] = (
    ("surname", "Фамилия:", "Исоев"),
    ("name", "Исм:", "Аслидин"),
    ("patronymic", "Отчество:", "Холбердиевич"),
    ("citizenship", "Гражданство:", "Таджикистан"),
    ("birth_place", "Туғилган жой:", "Таджикистан"),
    ("issued_by", "Ким берган:", "ГУ МВД России по г. Москве"),
    ("region", "Регион:", "77"),
    ("address", "Адрес:", "г Москва, ул Тагильская, д 45, кв 12"),
    ("position", "Должность:", "Подсобный рабочий"),
    ("organisation", "Ташкилот:", 'ООО "ГОРСТРОЙ"'),
    ("note", "Изоҳ:", "эркин матн"),
)
#: A box is shown when the form prints ANY of these keys.
_NEEDED_BY = {
    "surname": {"surname", "fio", "fio_upper"},
    "name": {"name", "fio", "fio_upper"},
    "patronymic": {"patronymic", "fio", "fio_upper"},
}


def _family(key: str) -> set[str]:
    """Every catalogue key a box feeds — a date feeds nine of them."""
    return _NEEDED_BY.get(key, {key})


def _date_family(prefix: str) -> set[str]:
    return {prefix, *(f"{prefix}_{tail}" for tail in
                      ("day", "month", "month_ru", "month_short", "year",
                       "year_short", "words", "short"))}


class UniversalView(QWidget):
    def __init__(self, controller: UniversalController) -> None:
        super().__init__()
        self._c = controller
        self._portrait: bytes | None = None
        self._boxes: dict[str, QLineEdit] = {}
        self._docs: dict[int, tuple[QLineEdit, QLineEdit]] = {}
        self._customs: dict[str, QLineEdit] = {}
        self._rows: dict[str, list[QWidget]] = {}

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

        title = QLabel("УНИВЕРСАЛ ИШЛАР — ўз бланкангиз, ўз матнларингиз")
        title.setObjectName("viewTitle")
        root.addWidget(title)
        note = QLabel(
            "Бўш бланкани юкланг → «📐 Созлаш» да матнларни қўйиб, жойини, "
            "рангини, шрифтини, катта-кичиклигини, тик-ётиғини белгиланг → "
            "ном билан сақланг. Кейин ўша бланкани танлаб, паспорт ва "
            "патентни ташлаб «Ўқиш» босасиз — майдонлар ўзи тўлади, "
            "текширасиз, «Тайёрлаш».")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8a94a3;")
        root.addWidget(note)

        # ------------------------------------------------------ the form
        blank_row = QHBoxLayout()
        blank_row.addWidget(QLabel("Бланка:"))
        self._blank = QComboBox()
        self._blank.setMinimumWidth(260)
        blank_row.addWidget(self._blank, stretch=1)
        for label, tip, slot in (
            ("➕ Бланка юклаш", "Бўш бланкани юклаб, ном беринг", self._add),
            ("📐 Созлаш", "Матнларни қўйиш, суриш, ранг-шрифт, тик-ётиқ, "
             "яқинлаштириш", self._arrange),
            ("✏️ Номини ўзгартириш", "", self._rename),
            ("🗑 Ўчириш", "Бланкани бутунлай ўчириш — фақат сиз айтсангиз",
             self._remove),
        ):
            button = QPushButton(label)
            if tip:
                button.setToolTip(tip)
            button.clicked.connect(slot)
            blank_row.addWidget(button)
        root.addLayout(blank_row)

        marks = QHBoxLayout()
        for which, label in ((STAMP, "🔴 Печать"), (SIGNATURE, "✒️ Имзо")):
            button = QPushButton(f"{label} юклаш")
            button.setToolTip("Шу бланка билан бирга сақланади — ҳар ишчида "
                              "қайта юклаш керак эмас")
            button.clicked.connect(lambda _=False, w=which: self._set_mark(w))
            marks.addWidget(button)
        self._marks = QLabel("")
        self._marks.setStyleSheet("color:#8a94a3;")
        marks.addWidget(self._marks, stretch=1)
        root.addLayout(marks)

        # -------------------------------------------------- the documents
        drops = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        drops.addWidget(self._passport)
        self._patent = DropZone("📄", "Патент (олди ва орқаси)", multiple=True)
        drops.addWidget(self._patent)
        self._photo = DropZone("🖼", "Ишчининг расми")
        drops.addWidget(self._photo)
        self._signature = DropZone("✒️", "Имзо (шу ишчиники)")
        drops.addWidget(self._signature)
        root.addLayout(drops)

        read_row = QHBoxLayout()
        read = QPushButton("📖 Ўқиш")
        read.setToolTip("Паспорт ва патентдан майдонларни тўлдиради")
        read.clicked.connect(self._read)
        read_row.addWidget(read)
        self._only_used = QCheckBox("Фақат шу бланка ишлатадиган майдонлар")
        self._only_used.setChecked(True)
        self._only_used.setToolTip("Бланка босмайдиган майдонлар яширилади")
        self._only_used.stateChanged.connect(self._show_rows)
        read_row.addWidget(self._only_used)
        read_row.addStretch(1)
        root.addLayout(read_row)

        # ------------------------------------------------------ the boxes
        self._form = QGroupBox("Маълумотлар")
        grid = QGridLayout(self._form)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        row = 0
        for key, label, hint in _BOXES:
            box = QLineEdit()
            box.setPlaceholderText(hint)
            name = QLabel(label)
            grid.addWidget(name, row, 0)
            grid.addWidget(box, row, 1, 1, 3)
            self._boxes[key] = box
            self._rows[key] = [name, box]
            row += 1

        # One field to a row. Pairing two across a row saves height, but the
        # moment one of a pair is hidden the other leaves a blank band beside
        # it, and this screen hides most of its rows most of the time.
        gender_label = QLabel("Жинси:")
        self._gender = QComboBox()
        self._gender.addItems(["Мужской", "Женский"])
        grid.addWidget(gender_label, row, 0)
        grid.addWidget(self._gender, row, 1, 1, 3)
        self._rows["gender"] = [gender_label, self._gender]
        row += 1

        for key, label, widget in (
            ("birth", "Туғилган сана:", QDateEdit(QDate(2000, 1, 1))),
            ("issued", "Берилган сана:", QDateEdit(QDate.currentDate())),
            ("expires", "Тугаш санаси:",
             QDateEdit(QDate.currentDate().addYears(1))),
        ):
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("dd.MM.yyyy")
            name = QLabel(label)
            grid.addWidget(name, row, 0)
            grid.addWidget(widget, row, 1, 1, 3)
            self._rows[key] = [name, widget]
            setattr(self, f"_{key}", widget)
            row += 1

        for slot in range(1, DOC_SLOTS + 1):
            label = QLabel(f"Ҳужжат {slot}:")
            series = QLineEdit()
            series.setPlaceholderText("серия")
            number = QLineEdit()
            number.setPlaceholderText("номер")
            grid.addWidget(label, row, 0)
            grid.addWidget(series, row, 1)
            grid.addWidget(number, row, 2, 1, 2)
            self._docs[slot] = (series, number)
            self._rows[f"doc{slot}"] = [label, series, number]
            row += 1

        self._grid = grid
        root.addWidget(self._form)

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
        self._status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._status)
        root.addStretch(1)

        self._reload()
        self._blank.currentIndexChanged.connect(self._on_blank)
        self._on_blank()

    # --------------------------------------------------------------- state
    def _name(self) -> str:
        return str(self._blank.currentData() or "")

    def _reload(self, keep: str = "") -> None:
        wanted = keep or self._name()
        self._blank.blockSignals(True)
        try:
            self._blank.clear()
            for name in self._c.names():
                self._blank.addItem(name, name)
            if self._blank.count() == 0:
                self._blank.addItem("— бланка юкланмаган —", "")
            elif wanted:
                at = self._blank.findData(wanted)
                if at >= 0:
                    self._blank.setCurrentIndex(at)
        finally:
            self._blank.blockSignals(False)

    def _on_blank(self) -> None:
        """A different form — its own custom boxes, and only its own rows."""
        self._rebuild_customs()
        self._show_rows()
        self._show_marks()

    def _rebuild_customs(self) -> None:
        """The boxes this form invented for itself, made afresh.

        Only the widgets are made here; `_show_rows` decides where they sit,
        so a form's own boxes land in the same run of rows as the rest.
        """
        for key in [k for k in self._rows if k.startswith("custom:")]:
            for widget in self._rows.pop(key):
                self._grid.removeWidget(widget)
                widget.deleteLater()
        self._customs.clear()

        for key in self._c.custom_keys(self._name()):
            label = QLabel(f"{self._c.label_of(key)}:")
            box = QLineEdit()
            box.setPlaceholderText("ўзингиз қўшган майдон")
            self._customs[key] = box
            self._rows[key] = [label, box]

    @staticmethod
    def _keys_of(row: str) -> set[str]:
        """Which catalogue keys a row feeds — a date feeds nine of them."""
        if row.startswith("doc"):
            slot = row[3:]
            return {f"doc{slot}_series", f"doc{slot}_number",
                    f"doc{slot}_full"}
        if row in ("birth", "issued", "expires"):
            return _date_family(row)
        return _family(row)

    def _show_rows(self) -> None:
        """Lay out only the rows this form prints.

        The grid is REBUILT rather than the unwanted rows merely hidden: a
        hidden widget still leaves its row's spacing behind, and with most of
        twenty-odd rows hidden the few that remain end up floating a
        centimetre apart. The widgets themselves are kept, so anything
        already typed survives the relayout.
        """
        used = self._c.wants(self._name())
        every = not self._only_used.isChecked() or not used

        for widgets in self._rows.values():
            for widget in widgets:
                self._grid.removeWidget(widget)
                widget.setVisible(False)

        at = 0
        for key, widgets in self._rows.items():
            if not (every or (self._keys_of(key) & used)):
                continue
            self._grid.addWidget(widgets[0], at, 0)
            if len(widgets) == 2:
                self._grid.addWidget(widgets[1], at, 1, 1, 3)
            else:                       # a серия/номер pair
                self._grid.addWidget(widgets[1], at, 1)
                self._grid.addWidget(widgets[2], at, 2, 1, 2)
            for widget in widgets:
                widget.setVisible(True)
            at += 1
        self._form.setVisible(at > 0)

    def _show_marks(self) -> None:
        name = self._name()
        said = []
        for which, label in ((STAMP, "печать"), (SIGNATURE, "имзо")):
            said.append(f"{label}: "
                        + ("✅" if self._c.picture_of(name, which) else "—"))
        self._marks.setText("Бланка билан сақланган — " + ", ".join(said))

    # ------------------------------------------------------- the library
    def _add(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "Бўш бланка", "",
            "Бланка (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tiff)")
        if not source:
            return
        name, ok = QInputDialog.getText(
            self, "Бланка номи",
            "Бу бланка нима деб аталсин?\n(масалан: Договор ТД, Уведомление)",
            text=Path(source).stem)
        if not ok or not name.strip():
            return
        try:
            saved = self._c.add(name.strip(), Path(source))
        except Exception as exc:                          # noqa: BLE001
            self._warn(str(exc))
            return
        self._reload(saved)
        self._on_blank()
        self._status.setText(
            f"✅ «{saved}» юкланди — энди «📐 Созлаш» да матнларни қўйинг.")

    def _rename(self) -> None:
        name = self._name()
        if not name:
            return
        into, ok = QInputDialog.getText(self, "Янги ном", "Ном:", text=name)
        if not ok or not into.strip():
            return
        try:
            saved = self._c.rename(name, into.strip())
        except Exception as exc:                          # noqa: BLE001
            self._warn(str(exc))
            return
        self._reload(saved)

    def _remove(self) -> None:
        name = self._name()
        if not name:
            return
        asked = QMessageBox.question(
            self, "Ўчириш",
            f"«{name}» бланкаси ва унга қўйилган ҳамма матнлар бутунлай "
            "ўчирилсинми? Бу қайтарилмайди.")
        if asked != QMessageBox.StandardButton.Yes:
            return
        self._c.remove(name)
        self._reload()
        self._on_blank()
        self._status.setText(f"🗑 «{name}» ўчирилди.")

    def _set_mark(self, which: str) -> None:
        name = self._name()
        if not name:
            self._warn("Аввал бланка танланг.")
            return
        source, _ = QFileDialog.getOpenFileName(
            self, "Расм", "", "Расм (*.png *.jpg *.jpeg)")
        if not source:
            return
        try:
            self._c.set_picture(name, which, Path(source))
        except Exception as exc:                          # noqa: BLE001
            self._warn(str(exc))
            return
        self._show_marks()

    def _arrange(self) -> None:
        name = self._name()
        if not name:
            self._warn("Аввал бланка юкланг.")
            return
        from src.ui.widgets.field_editor import FieldEditor

        try:
            pages = self._c.pages(name)
        except Exception as exc:                          # noqa: BLE001
            self._warn(str(exc))
            return
        placed = self._c.fields(name)
        keys = [f.key for f in placed]
        editor = FieldEditor(pages, placed, title=name, parent=self,
                             catalogue=self._c.catalogue(keys),
                             samples=self._c.samples(keys))
        if editor.exec() != FieldEditor.DialogCode.Accepted:
            return
        self._c.save_fields(name, editor.fields())
        self._on_blank()
        self._status.setText(f"✅ «{name}» — матнлар сақланди.")

    # ------------------------------------------------------------ reading
    def _read(self) -> None:
        passport = (Path(self._passport.path).read_bytes()
                    if self._passport.path else None)
        patent_paths = self._patent.paths
        patent = (Path(patent_paths[0]).read_bytes() if patent_paths else None)
        if passport is None and patent is None:
            self._warn("Паспорт ёки патент расмини ташланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        self._run.setEnabled(False)
        self._progress.start("Ҳужжатлар ўқиляпти…")
        run_async(lambda: self._c.read(passport, patent),
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, data: UniversalData) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        for key in ("surname", "name", "patronymic", "citizenship",
                    "birth_place", "position"):
            said = getattr(data, key, "")
            if said:
                self._boxes[key].setText(said)
        if data.gender:
            self._gender.setCurrentText(data.gender)
        for widget, when in ((self._birth, data.birth_date),
                             (self._issued, data.issued),
                             (self._expires, data.expires)):
            if when:
                widget.setDate(QDate(when.year, when.month, when.day))
        for slot, (series, number) in (data.documents or {}).items():
            if slot in self._docs:
                self._docs[slot][0].setText(series)
                self._docs[slot][1].setText(number)
        self._status.setText("✅ Ўқилди — текширинг ва «Тайёрлаш».")

    # ------------------------------------------------------------- making
    def _data(self) -> UniversalData:
        """What is in the boxes — never what was read."""
        made = UniversalData(
            gender=self._gender.currentText(),
            birth_date=self._birth.date().toPython(),
            issued=self._issued.date().toPython(),
            expires=self._expires.date().toPython())
        for key, box in self._boxes.items():
            setattr(made, key, box.text().strip())
        for slot, (series, number) in self._docs.items():
            made.documents[slot] = (series.text().strip(),
                                    number.text().strip())
        made.custom = {k: b.text().strip() for k, b in self._customs.items()}
        made.photo_png = self._portrait
        if self._signature.path:
            made.signature_png = Path(self._signature.path).read_bytes()
        return made

    def _generate(self) -> None:
        name = self._name()
        if not name:
            self._warn("Бланка юкланмаган — «➕ Бланка юклаш».")
            return
        if not self._c.fields(name):
            self._warn(f"«{name}» да матн жойлаштирилмаган — «📐 Созлаш».")
            return
        if self._photo.path and self._portrait is None:
            self._portrait = self._c.portrait(
                Path(self._photo.path).read_bytes())
        data = self._data()
        self._run.setEnabled(False)
        self._progress.start("Тайёрланяпти…")
        run_async(lambda: self._c.generate(name, data),
                  on_success=self._made, on_error=self._failed)

    def _made(self, result: UniversalResult) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._status.setText(f"✅ Тайёр: {result.pdf.name} — «{result.form}»")
        from src.ui.widgets.save_to import ask_save_dir

        ask_save_dir(self, [result.pdf])

    def _failed(self, exc: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._status.setText(f"❌ {exc}")
        self._warn(str(exc))

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self, "УНИВЕРСАЛ", text)

    def reset(self) -> None:
        for zone in (self._passport, self._patent, self._photo,
                     self._signature):
            zone.clear()
        self._portrait = None
        self._status.setText("")


__all__ = ["UniversalView"]
