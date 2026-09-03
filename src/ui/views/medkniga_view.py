"""МЕД КНИЖКА — the four pages the office prints for the medical commission.

The office drops the worker's photograph and one of his documents, types
the booklet number off the booklet in its hand, picks the date, the trade
and the town, and gets four pages ready for the printer. The examination
itself and every stamp stay with the commission — the program only writes
what the office already writes by hand.

Everything on those pages can be dragged, resized, recoloured and set in
any installed font in ONE window, and the office may add texts of its own.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.medkniga_controller import MedKnigaController
from src.pdf.medkniga_renderer import stamp_date
from src.pdf.medkniga_spec import ALL_SLOTS, PAGES
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

#: The towns the office writes on the holder's page, and «boshqa» for the rest.
_CITIES = ("Москва", "Московская область")
#: The trades it hires for — a starting list, and any other may be typed.
_TRADES = ("Помощник повара", "Повар", "Кухонный рабочий", "Официант",
           "Уборщик", "Грузчик", "Подсобный рабочий", "Продавец",
           "Мойщик посуды", "Пекарь")


class MedKnigaView(QWidget):
    def __init__(self, controller: MedKnigaController) -> None:
        super().__init__()
        self._c = controller
        self._signature: Path | None = None
        self._signature_png: bytes | None = None

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

        title = QLabel("МЕД КНИЖКА — 4 бет")
        title.setObjectName("viewTitle")
        root.addWidget(title)
        note = QLabel(
            "Программа фақат сиз ёзадиган маълумотни ёзади: ишчи, санаси, "
            "лавозими, китоб рақами. Кўрикни ва печатни мед комиссия ўзи "
            "қилади.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8a94a3;")
        root.addWidget(note)

        kit_row = QHBoxLayout()
        kit_row.addWidget(QLabel("Комплект:"))
        self._kit = QComboBox()
        for key, label in self._c.kits().items():
            self._kit.addItem(label, key)
        self._kit.setToolTip("Бланкалари бошқа-бошқа; матн, расм ва имзо "
                             "иккисида ҳам бир хил жойда туради")
        self._kit.currentIndexChanged.connect(self._kit_chosen)
        kit_row.addWidget(self._kit, stretch=1)
        kit_row.addStretch(2)
        root.addLayout(kit_row)

        docs = QHBoxLayout()
        self._photo = DropZone("🖼", "Ишчи расми")
        docs.addWidget(self._photo)
        self._document = DropZone("🛂", "Паспорт ёки патент")
        self._document.changed.connect(self._on_dropped)
        docs.addWidget(self._document)
        root.addLayout(docs)

        # what was read, for the operator to check before printing
        from src.ui.widgets.passport_review import PassportReview
        self._review = PassportReview()
        root.addWidget(self._review)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(400)
        self._settle.timeout.connect(self._read_now)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        root.addLayout(form)

        form.addWidget(QLabel("Кўрик санаси:"), 0, 0)
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.dateChanged.connect(self._show_dates)
        form.addWidget(self._date, 0, 1)

        form.addWidget(QLabel("Китоб рақами:"), 0, 2)
        self._number = QLineEdit(self._c.next_number())
        self._number.setPlaceholderText("масалан 8832888")
        form.addWidget(self._number, 0, 3)

        form.addWidget(QLabel("Лавозими:"), 1, 0)
        self._trade = QComboBox()
        self._trade.setEditable(True)
        self._trade.addItems(_TRADES)
        form.addWidget(self._trade, 1, 1)

        form.addWidget(QLabel("Адрес:"), 1, 2)
        self._city = QComboBox()
        self._city.setEditable(True)
        self._city.addItems(_CITIES)
        form.addWidget(self._city, 1, 3)

        self._dates = QLabel("")
        self._dates.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._dates)

        tools = QHBoxLayout()
        blanks = QPushButton("📄 Бланкалар")
        blanks.setToolTip("Ҳар бетнинг ўз бланкасини юклаш — бўш қолдирса "
                          "оқ саҳифага чиқади")
        blanks.clicked.connect(self._blanks)
        tools.addWidget(blanks)
        signature = QPushButton("✍ Имзо чизиш")
        signature.setToolTip("Ишчи шу ерда имзо қўяди — 1-бетга тушади")
        signature.clicked.connect(self._draw_signature)
        tools.addWidget(signature)
        signature_file = QPushButton("📎 Имзо расми")
        signature_file.setToolTip("Ёки имзонинг тайёр расмини юкланг")
        signature_file.clicked.connect(self._pick_signature)
        tools.addWidget(signature_file)
        seal = QPushButton("⬤ Печать")
        seal.setToolTip("Фирманинг ўз печати — бир марта юкланади ва ҳар "
                        "ишчига ишлатилади")
        seal.clicked.connect(self._pick_stamp)
        tools.addWidget(seal)
        arrange = QPushButton("📐 Созлаш")
        arrange.setToolTip("Матнларни суриш, катта-кичик қилиш, ранг ва "
                           "шрифт танлаш, матн қўшиш")
        arrange.clicked.connect(self._arrange)
        tools.addWidget(arrange)
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
        self._show_dates()

    # -------------------------------------------------------------- state
    def _when(self) -> date:
        return self._date.date().toPython()

    def _kit_key(self) -> str:
        return str(self._kit.currentData() or "moskva")

    def _kit_chosen(self) -> None:
        """The kit says which town the holder's page carries by default."""
        self._city.setCurrentText(self._kit.currentText())
        have = len(self._c.blanks(self._kit_key()))
        self._status.setText(
            f"«{self._kit.currentText()}» танланди — {have}/{PAGES} бланка "
            "юкланган." if have else
            f"«{self._kit.currentText()}» танланди — бланкаси йўқ, оқ "
            "саҳифага чиқади.")

    def _show_dates(self) -> None:
        from src.pdf.medkniga_renderer import a_year_on

        when = self._when()
        self._dates.setText(
            f"Китобда: {stamp_date(when)} · тугаши "
            f"{stamp_date(a_year_on(when))}")

    # ------------------------------------------------------------- blanks
    def _blanks(self) -> None:
        kit = self._kit_key()
        have = self._c.blanks(kit)
        lines = "\n".join(
            f"  {p}-бет: {'✅ ' + have[p].name if p in have else '— йўқ (оқ)'}"
            for p in range(1, PAGES + 1))
        box = QMessageBox(self)
        box.setWindowTitle(f"Бланкалар — {self._kit.currentText()}")
        box.setText(f"«{self._kit.currentText()}» комплекти:\n{lines}\n\n"
                    "Қайси бетни юкласиз?")
        buttons = {}
        for page in range(1, PAGES + 1):
            buttons[box.addButton(f"{page}-бет",
                                  QMessageBox.ButtonRole.ActionRole)] = page
        clear = box.addButton("🗑 Ҳаммасини тозалаш",
                              QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Ёпиш", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        picked = box.clickedButton()
        if picked is clear:
            for page in range(1, PAGES + 1):
                self._c.clear_blank(page, kit)
            self._status.setText(
                f"✅ «{self._kit.currentText()}» бланкалари тозаланди — оқ "
                "саҳифага чиқади.")
            return
        page = buttons.get(picked)
        if page is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, f"{self._kit.currentText()} — {page}-бет бланкаси", "",
            "Бланка (*.pdf *.png *.jpg *.jpeg)")
        if not path:
            return
        try:
            self._c.set_blank(page, Path(path), kit)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(
            f"✅ «{self._kit.currentText()}» — {page}-бет бланкаси юкланди.")

    def _draw_signature(self) -> None:
        """The worker signs here, with the mouse or a finger."""
        from PySide6.QtWidgets import QDialog

        from src.ui.widgets.signature_pad import SignaturePad

        pad = SignaturePad(self)
        pad.set_ink((0, 14, 168))            # the booklet's own blue
        if pad.exec() != QDialog.DialogCode.Accepted:
            return
        self._signature_png = pad.signature_png()
        self._signature = None
        self._status.setText("✅ Имзо олинди — жойини «📐 Созлаш» да "
                             "белгиланг.")

    def _pick_signature(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Ишчининг имзоси (шаффоф PNG яхши)", "",
            "Расм (*.png *.jpg *.jpeg)")
        if not path:
            return
        self._signature = Path(path)
        self._signature_png = Path(path).read_bytes()
        self._status.setText(f"✅ Имзо танланди: {Path(path).name} — жойини "
                             "«📐 Созлаш» да белгиланг.")

    def _pick_stamp(self) -> None:
        """The firm's own seal — uploaded once, used for every worker."""
        have = self._c.stamp()
        if have is not None:
            box = QMessageBox(self)
            box.setWindowTitle("Печать")
            box.setText(f"Ҳозирги печать: {have.name}\n\nНима қиламиз?")
            change = box.addButton("Алмаштириш",
                                   QMessageBox.ButtonRole.ActionRole)
            drop = box.addButton("🗑 Ўчириш",
                                 QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Ёпиш", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is drop:
                self._c.clear_stamp()
                self._status.setText("✅ Печать ўчирилди.")
                return
            if box.clickedButton() is not change:
                return
        path, _ = QFileDialog.getOpenFileName(
            self, "Фирманинг печати (шаффоф PNG яхши)", "",
            "Расм (*.png *.jpg *.jpeg)")
        if not path:
            return
        try:
            self._c.set_stamp(Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(f"✅ Печать юкланди: {Path(path).name} — жойини "
                             "«📐 Созлаш» да белгиланг.")

    # ------------------------------------------------------------ arrange
    def _arrange(self) -> None:
        import fitz

        from src.pdf.medkniga_renderer import (
            MedKnigaData,
            placed,
            placed_images,
            render,
        )
        from src.pdf.medkniga_spec import IMG_LABELS
        from src.pdf.trud8_fields import Field
        from src.ui.widgets.field_editor import FieldEditor

        # the picture under the marks is the section's own output, so what
        # is dragged is dragged over exactly what the printer will put out
        sample = MedKnigaData(
            surname="Расулов", name="Азиз", patronymic="Расулжон Угли",
            birth_year="1992", city=self._city.currentText(),
            position=self._trade.currentText() or "Помощник повара",
            number=self._number.text() or "8832888", exam_date=self._when(),
            blanks=self._c.blanks(self._kit_key()), layout={})
        try:
            with fitz.open("pdf", render(sample)) as doc:
                pages = [p.get_pixmap(dpi=52).tobytes("png") for p in doc]
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        layout = self._c.layout()
        slots = placed(layout)
        catalogue = {k: s.label or k for k, s in ALL_SLOTS.items()}
        samples = {k: s.sample for k, s in ALL_SLOTS.items()}
        fields = [
            Field(key=key, page=slot.page, x=slot.x, baseline=slot.baseline,
                  size=slot.size, colour=tuple(slot.colour)[:3],
                  bold=slot.bold, font=slot.family, rotate=slot.rotate)
            for key, slot in slots.items()]
        for index, extra in enumerate(layout.get("extra") or []):
            key = f"extra{index}"
            catalogue[key] = f"Қўшимча матн {index + 1}"
            samples[key] = str(extra.get("text") or "матн")
            fields.append(Field(
                key=key, page=int(extra.get("page", 1)),
                x=float(extra.get("x", 0.1)),
                baseline=float(extra.get("baseline", 0.1)),
                size=float(extra.get("size", 0.013)),
                colour=tuple(extra.get("colour") or (0.0, 0.0, 0.0))[:3],
                bold=bool(extra.get("bold", False)),
                font=str(extra.get("font") or "Arial"),
                rotate=int(extra.get("rotate", 0))))

        # the photograph and the signature are dragged like anything else,
        # and the REAL picture is what is dragged — so what is on screen is
        # the size and the place they will print at
        pictures: dict[str, bytes] = {}
        if self._photo.path is not None:
            pictures["img_photo"] = Path(self._photo.path).read_bytes()
        if self._signature_png:
            pictures["img_sign"] = self._signature_png
        seal = self._c.stamp()
        if seal is not None:
            pictures["img_stamp"] = seal.read_bytes()
        for key, (page_no, x, bottom, height) in placed_images(layout).items():
            catalogue[key] = IMG_LABELS[key]
            samples[key] = IMG_LABELS[key]
            fields.append(Field(key=key, page=page_no, x=x, baseline=bottom,
                                size=height, colour=(0.0, 0.0, 0.0),
                                bold=False, font="Arial"))

        dialog = FieldEditor(pages, fields, title="Мед книжка", parent=self,
                             catalogue=catalogue, samples=samples,
                             frozen=set(ALL_SLOTS) | set(IMG_LABELS),
                             images=pictures)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        new_fields: dict[str, list[float]] = {}
        new_styles: dict[str, dict] = {}
        new_extra: list[dict] = []
        new_images: dict[str, list] = {}
        for made in dialog.fields():
            if made.key in IMG_LABELS:
                new_images[made.key] = [made.page, round(made.x, 5),
                                        round(made.baseline, 5),
                                        round(made.size, 5)]
            elif made.key in ALL_SLOTS:
                new_fields[made.key] = [round(made.x, 5),
                                        round(made.baseline, 5),
                                        round(made.size, 5)]
                new_styles[made.key] = {"font": made.font, "bold": made.bold,
                                        "colour": list(made.colour),
                                        "rotate": made.rotate,
                                        "size": round(made.size, 5)}
            else:
                new_extra.append({
                    "text": samples.get(made.key, "матн"), "page": made.page,
                    "x": round(made.x, 5), "baseline": round(made.baseline, 5),
                    "size": round(made.size, 5), "font": made.font,
                    "bold": made.bold, "rotate": made.rotate,
                    "colour": list(made.colour)})
        self._c.save_layout({"fields": new_fields, "styles": new_styles,
                             "extra": new_extra, "images": new_images})
        self._status.setText("✅ Жойлар ва созламалар сақланди — иккала "
                             "комплектга ҳам тегишли.")

    # ----------------------------------------------------------- reading
    def _on_dropped(self) -> None:
        """The document landed — read it after a short settle."""
        if self._document.path is None or not self._c.ai_available():
            return
        self._settle.start()

    def _read_now(self) -> None:
        if self._document.path is None or not self._c.ai_available():
            return
        document = self._c.read_image(self._document.path)
        is_patent = "патент" in Path(self._document.path).name.lower()
        self._status.setText("⏳ Ҳужжат ўқиляпти…")
        self._progress.start("Ҳужжат ўқиляпти…")
        run_async(self._c.read_document, document, is_patent=is_patent,
                  on_success=self._filled, on_error=self._read_failed)

    def _filled(self, passport) -> None:
        self._progress.finish()
        self._review.fill(passport)
        self._status.setText("✅ Ўқилди — текширинг, хатоси бўлса тўғриланг, "
                             "кейин Тайёрлаш.")

    def _read_failed(self, error: Exception) -> None:
        self._progress.finish()
        self._review.reveal()          # so it can be typed by hand
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ Ўқилмади: {message}. Қўлда ёзинг.")

    # ---------------------------------------------------------- printing
    def _generate(self) -> None:
        if self._document.path is None and self._review.isHidden():
            self._warn("Паспорт ёки патент расмини ташланг.")
            return
        if self._review.isHidden():
            self._warn("Ҳужжат ҳали ўқилмади — бир оз кутинг.")
            return
        if not self._review.has_surname():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return
        if not self._number.text().strip():
            self._warn("Китоб рақамини киритинг.")
            return
        photo = (Path(self._photo.path).read_bytes()
                 if self._photo.path is not None else None)
        signature = self._signature_png
        position = self._trade.currentText().strip()
        city = self._city.currentText().strip() or "Москва"
        number = self._number.text().strip()
        when = self._when()

        self._run.setEnabled(False)
        self._progress.start("Тўрт бет тайёрланаяпти…")

        kit = self._kit_key()
        run_async(
            self._c.print_document, self._review.edited(),
            position=position, city=city, number=number, exam_date=when,
            photo_png=photo, signature_png=signature, kit=kit,
            on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._document.clear()
        self._photo.clear()
        self._review.reset()
        self._number.setText(self._c.next_number())
        self._status.setText(
            f"✅ Тайёр: {result.pdf_path.name} · № {result.number} · "
            f"{stamp_date(result.exam_date)} → {stamp_date(result.expires)}")
        from src.ui.widgets.save_to import ask_save_dir

        ask_save_dir(self, [result.pdf_path])

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        made = paths.output_dir() / "medkniga"
        made.mkdir(parents=True, exist_ok=True)
        _open_folder(made)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        self._photo.clear()
        self._document.clear()
