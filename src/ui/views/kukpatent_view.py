"""КУК ПАТЕНТ — the card the office prints on its own two scans.

The office drops the worker's passport and his photograph, types the серия
and номер off the card in its hand, picks the firm and the day, and gets
both sides ready for the printer. Everything the reader offers lands in a
box it can type over first.

The card's own number is offered already stepped on by two, so a run of
workers needs no typing at all after the first.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.kukpatent_controller import KukPatentController
from src.pdf.kukpatent_renderer import KukPatentData
from src.pdf.kukpatent_spec import FRONT, PHOTO_KEY, PHOTO_LABEL
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class KukPatentView(QWidget):
    def __init__(self, controller: KukPatentController) -> None:
        super().__init__()
        self._c = controller
        self._portrait: bytes | None = None

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

        title = QLabel("КУК ПАТЕНТ — олди ва орқаси")
        title.setObjectName("viewTitle")
        root.addWidget(title)
        note = QLabel(
            "Паспорт ва ишчининг расмини ташланг → «Ўқиш» → серия-номерни "
            "ёзинг, фирма ва числони танланг → «Тайёрлаш». Расм оқ фонда "
            "3×4 қилиб кесилади ва рамкага тушади. Матн ва расм 85% да "
            "ётади — қоғозга сингиб кетсин деб.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8a94a3;")
        root.addWidget(note)

        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        docs.addWidget(self._passport)
        self._photo = DropZone("🖼", "Ишчининг расми")
        docs.addWidget(self._photo)
        read = QPushButton("📖 Ўқиш")
        read.setToolTip("Паспортдан ФИО, туғилган сана, жинси, гражданство "
                        "ва ҳужжат рақами")
        read.clicked.connect(self._read)
        docs.addWidget(read)
        root.addLayout(docs)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        root.addLayout(form)

        self._surname = self._box(form, 0, 0, "Фамилия:", "Эргешов")
        self._name = self._box(form, 0, 2, "Имя:", "Омурбек")
        self._patronymic = self._box(form, 1, 0, "Отчество:", "Куштарович")
        self._citizenship = self._box(form, 1, 2, "Гражданство:", "Киргизия")
        self._document = self._box(form, 2, 0, "Ҳужжат:",
                                   "Иностранный паспорт ID3956001")
        self._document.setToolTip("Орқа томондаги «Документ, удостоверяющий "
                                  "личность» қатори")

        form.addWidget(QLabel("Жинси:"), 2, 2)
        self._gender = QComboBox()
        self._gender.addItems(["М", "Ж"])
        form.addWidget(self._gender, 2, 3)

        form.addWidget(QLabel("Туғилган сана:"), 3, 0)
        self._born = QDateEdit(QDate(2000, 1, 1))
        self._born.setCalendarPopup(True)
        self._born.setDisplayFormat("dd.MM.yyyy")
        form.addWidget(self._born, 3, 1)

        form.addWidget(QLabel("Берилган сана:"), 3, 2)
        self._issued = QDateEdit(QDate.currentDate())
        self._issued.setCalendarPopup(True)
        self._issued.setDisplayFormat("dd.MM.yyyy")
        self._issued.setToolTip("Картанинг орқасидаги «Дата выдачи»")
        form.addWidget(self._issued, 3, 3)

        self._series = self._box(form, 4, 0, "Серия:", "88")
        self._number = self._box(form, 4, 2, "Номер:", "3259366")

        form.addWidget(QLabel("Картанинг рақами:"), 5, 0)
        self._card_no = QLineEdit(self._c.next_number())
        self._card_no.setPlaceholderText("АА3915699")
        self._card_no.setToolTip("Кейинги ишчига ўзи иккитага ошиб туради — "
                                 "биринчисини бир марта ёзиб қўйинг")
        form.addWidget(self._card_no, 5, 1)

        form.addWidget(QLabel("Фирма:"), 6, 0)
        self._firm = QComboBox()
        self._firm.setEditable(True)
        self._firm.setToolTip("Ёзилган фирма сақланиб қолади — кейинги "
                              "сафар рўйхатдан танлайсиз")
        form.addWidget(self._firm, 6, 1, 1, 3)
        self._show_firms()

        form.addWidget(QLabel("Фирмани ўзингиз бўлиш:"), 7, 0)
        self._firm2 = QPlainTextEdit()
        self._firm2.setFixedHeight(48)
        self._firm2.setPlaceholderText(
            "Ихтиёрий. Картадаги «Документ выдан» иккита қаторга сиғади — "
            "қаерда бўлинишини ўзингиз белгиламоқчи бўлсангиз, 1-қаторни "
            "ёзиб Enter босинг ва 2-қаторни ёзинг. Бўш қолса ўзи бўлади.")
        self._firm2.setToolTip("Бўш бўлса — юқоридаги фирма ишлатилади")
        form.addWidget(self._firm2, 7, 1, 1, 3)

        tools = QHBoxLayout()
        for label, tip, slot in (
            ("📄 Бланкалар", "Олди ва орқасининг ўз скани — бир марта",
             self._blanks),
            ("🗑 Фирмани ўчириш", "Рўйхатдан керак бўлмаганини олиб ташлаш",
             self._forget_firm),
            ("📐 Созлаш", "Матн ва расмни суриш, катта-кичик қилиш, "
             "қалин-юпқа, ранг", self._arrange),
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
        """The saved firms, each shown on ONE line but kept as it was typed.

        A firm the office broke across two lines carries a newline, and a
        combo box makes a mess of one — so the break is hidden in the list
        and handed back whole when that firm is picked.
        """
        kept = self._firm.currentText()
        self._firm.clear()
        for firm in self._c.firms():
            self._firm.addItem(" ".join(firm.split()), firm)
        self._firm.setCurrentText(kept)

    def _firm_text(self) -> str:
        """What goes on the card: the two typed lines, or the picked firm."""
        broken = self._firm2.toPlainText().strip()
        if broken:
            return broken
        shown = self._firm.currentText().strip()
        index = self._firm.findText(shown)
        if index >= 0 and self._firm.itemData(index):
            return str(self._firm.itemData(index))
        return shown

    def _data(self) -> KukPatentData:
        """What is in the boxes — never what was read, always what is shown."""
        return KukPatentData(
            surname=self._surname.text().strip(),
            name=self._name.text().strip(),
            patronymic=self._patronymic.text().strip(),
            birth_date=self._born.date().toPython(),
            gender=self._gender.currentText().strip(),
            citizenship=self._citizenship.text().strip(),
            document=self._document.text().strip(),
            series=self._series.text().strip(),
            number=self._number.text().strip(),
            firm=self._firm_text(),
            issued=self._issued.date().toPython(),
            card_no=self._card_no.text().strip(),
            photo_png=self._portrait)

    # ------------------------------------------------------------- reading
    def _read(self) -> None:
        if self._passport.path is None:
            self._warn("Паспорт расмини ташланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        image = Path(self._passport.path).read_bytes()
        photo = (Path(self._photo.path).read_bytes()
                 if self._photo.path is not None else None)
        firm, series = self._firm_text(), self._series.text().strip()
        number, when = self._number.text().strip(), self._issued.date().toPython()
        card_no = self._card_no.text().strip()

        self._run.setEnabled(False)
        self._progress.start("Паспорт ўқилиб, расм кесиляпти…")
        run_async(lambda: self._c.read_passport(
            image, firm=firm, series=series, number=number, issued=when,
            card_no=card_no, photo=photo),
            on_success=self._filled, on_error=self._failed)

    def _filled(self, data: KukPatentData) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._surname.setText(data.surname)
        self._name.setText(data.name)
        self._patronymic.setText(data.patronymic)
        self._citizenship.setText(data.citizenship)
        self._document.setText(data.document)
        self._gender.setCurrentText(data.gender or "М")
        if data.birth_date:
            self._born.setDate(QDate(data.birth_date.year,
                                     data.birth_date.month,
                                     data.birth_date.day))
        self._portrait = data.photo_png
        self._status.setText(
            "✅ Ўқилди — текширинг ва «Тайёрлаш»." if data.photo_png else
            "✅ Ўқилди. Расм ташланмади — картада фақат матн бўлади.")

    # -------------------------------------------------------------- blanks
    def _blanks(self) -> None:
        have = self._c.blanks()
        names = self._c.side_names()
        lines = "\n".join(
            f"  {names[s]}: {'✅ ' + have[s].name if s in have else '— йўқ'}"
            for s in self._c.sides())
        box = QMessageBox(self)
        box.setWindowTitle("Бланкалар")
        box.setText(f"{lines}\n\nҚайси томонни юкласиз?")
        buttons = {}
        for side in self._c.sides():
            buttons[box.addButton(names[side],
                                  QMessageBox.ButtonRole.ActionRole)] = side
        clear = box.addButton("🗑 Иккаласини тозалаш",
                              QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Ёпиш", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        picked = box.clickedButton()
        if picked is clear:
            for side in self._c.sides():
                self._c.clear_blank(side)
            self._status.setText("✅ Бланкалар тозаланди.")
            return
        side = buttons.get(picked)
        if side is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, f"{names[side]} бланкаси", "",
            "Бланка (*.pdf *.png *.jpg *.jpeg)")
        if not path:
            return
        try:
            self._c.set_blank(side, Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(f"✅ {names[side]} бланкаси юкланди.")

    def _forget_firm(self) -> None:
        firm = self._firm.currentText().strip()
        if not firm:
            self._warn("Ўчириш учун фирмани танланг.")
            return
        if QMessageBox.question(
                self, "Фирмани ўчириш",
                f"«{firm}» рўйхатдан ўчирилсинми?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._c.forget_firm(firm)
        self._show_firms()
        self._status.setText(f"✅ «{firm}» рўйхатдан ўчирилди.")

    # ------------------------------------------------------------- arrange
    def _arrange(self) -> None:
        """Both sides in one window — each remembers its own places."""
        import fitz

        from src.pdf.kukpatent_renderer import render
        from src.ui.widgets.field_editor import FieldEditor

        sides = self._c.sides()
        blanks = self._c.blanks()
        sample = self._data()
        if not sample.surname:
            sample = KukPatentData(
                surname="Эргешов", name="Омурбек", patronymic="Куштарович",
                birth_date=date(1998, 6, 16), gender="М",
                citizenship="Киргизия",
                document="Иностранный паспорт ID3956001",
                series="88", number="3259366",
                firm='ООО "Сфера" отдел кадров', issued=date(2024, 9, 3),
                card_no="АА3915699", photo_png=self._portrait)
        try:
            pages = []
            for side in sides:
                with fitz.open("pdf", render(sample, side,
                                             blanks.get(side))) as doc:
                    pages.append(doc[0].get_pixmap(dpi=110).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        catalogue, samples, fields = to_fields(sides, self._c.layout())
        pictures = {f"{FRONT}:{PHOTO_KEY}": self._portrait} \
            if self._portrait else {}
        dialog = FieldEditor(pages, fields, title="Кук патент", parent=self,
                             catalogue=catalogue, samples=samples,
                             frozen=set(catalogue), images=pictures)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._c.save_layout(to_layout(dialog.fields(), samples, sides))
        self._status.setText("✅ Жойлар ва созламалар сақланди.")

    # ------------------------------------------------------------ printing
    def _generate(self) -> None:
        if not self._surname.text().strip():
            self._warn("Фамилия бўш — паспортни ўқитинг ёки ўзингиз ёзинг.")
            return
        if not self._firm_text():
            self._warn("Фирмани танланг ёки ёзинг.")
            return
        data = self._data()
        self._run.setEnabled(False)
        self._progress.start("Картанинг икки томони тайёрланяпти…")
        run_async(lambda: self._c.generate(data),
                  on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._card_no.setText(self._c.next_number())
        self._show_firms()
        self._status.setText(
            f"✅ Тайёр: {result.surname} · № {result.card_no} · {result.firm}")
        from src.ui.widgets.save_to import ask_save_dir

        ask_save_dir(self, [result.pdfs[s] for s in self._c.sides()
                            if s in result.pdfs])

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.services.kukpatent_service import SECTION
        from src.ui.views.settings_view import _open_folder

        made = paths.output_dir() / SECTION
        made.mkdir(parents=True, exist_ok=True)
        _open_folder(made)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        self._passport.clear()
        self._photo.clear()
        self._portrait = None


# ---------------------------------------------------------- the arranger
# Both sides go into ONE editor window, and the editor knows a text by its
# key alone — so every key goes in wearing its side: «back:issued» is not
# «front:series», and dragging one leaves the other where the office put it.
def to_fields(sides, layout: dict):
    """(catalogue, samples, fields) for the editor, side by side."""
    from src.pdf.kukpatent_renderer import placed, placed_photo
    from src.pdf.kukpatent_spec import PAGE_H, PAGE_W, SIDE_NAMES
    from src.pdf.trud8_fields import Field

    catalogue: dict[str, str] = {}
    samples: dict[str, str] = {}
    fields: list = []
    for index, side in enumerate(sides, start=1):
        for key, slot in placed(side, layout).items():
            tag = f"{side}:{key}"
            catalogue[tag] = f"{SIDE_NAMES[side]} · {slot.label or key}"
            samples[tag] = slot.sample or key
            fields.append(Field(
                key=tag, page=index, x=slot.x, baseline=slot.baseline,
                size=slot.size, colour=tuple(slot.colour)[:3],
                bold=slot.bold, font=slot.family))
        if side != FRONT:
            continue
        left, top, _width, height = placed_photo(layout)
        tag = f"{side}:{PHOTO_KEY}"
        catalogue[tag] = f"{SIDE_NAMES[side]} · {PHOTO_LABEL}"
        samples[tag] = PHOTO_LABEL
        # the editor works in «left, BOTTOM, height»; the width follows the
        # height because the picture keeps its 3×4 whatever is dragged
        fields.append(Field(key=tag, page=index, x=left, baseline=top + height,
                            size=height, colour=(0.0, 0.0, 0.0), bold=False,
                            font="Arial"))
        _ = PAGE_W, PAGE_H
    return catalogue, samples, fields


def to_layout(fields, samples: dict[str, str], sides) -> dict:
    """What the editor left, in the shape the renderer reads back."""
    made: dict[str, dict] = {"fields": {}, "styles": {}, "images": {}}
    extra: list[dict] = []
    order = list(sides)
    for field in fields:
        side, _, key = field.key.partition(":")
        place = [round(field.x, 5), round(field.baseline, 5),
                 round(field.size, 5)]
        if not key:                        # a text the office added itself
            page = max(1, min(len(order), int(field.page)))
            extra.append({"text": samples.get(field.key, "матн"),
                          "side": order[page - 1], "x": place[0],
                          "baseline": place[1], "size": place[2],
                          "font": field.font, "bold": field.bold,
                          "colour": list(field.colour)})
        elif key == PHOTO_KEY:
            made["images"].setdefault(side, {})[key] = place
        else:
            made["fields"].setdefault(side, {})[key] = place
            made["styles"].setdefault(side, {})[key] = {
                "font": field.font, "bold": field.bold,
                "colour": list(field.colour), "size": place[2]}
    return {**made, "extra": extra}
