"""АЛПИНИСТ — the industrial climber's card, start to finish in one press.

Passport + patent give the ФИО; the worker's snapshot is cleaned to a white
ground and cut 3×4 into the card's frame; the worker signs with the mouse in
ink; the back's blank number counts up on its own. The печать is uploaded
once and — like every text — can be dragged and resized on the blank.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
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
from src.controllers.alpinist_controller import AlpinistController
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class AlpinistView(QWidget):
    def __init__(self, controller: AlpinistController) -> None:
        super().__init__()
        self._c = controller
        self._signature: bytes | None = None

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

        title = QLabel("АЛПИНИСТ — промышленный альпинист удостоверенияси")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- blank + печать --------------------------------------------
        blank_row = QHBoxLayout()
        blank_row.addWidget(QLabel("Бланка:"))
        self._template = QComboBox()
        blank_row.addWidget(self._template, stretch=1)
        add_blank = QPushButton("➕ Бланка")
        add_blank.clicked.connect(self._add_template)
        blank_row.addWidget(add_blank)
        drop_blank = QPushButton("🗑")
        drop_blank.setToolTip("Танланган бланкани ўчириш")
        drop_blank.clicked.connect(self._remove_template)
        blank_row.addWidget(drop_blank)
        arrange = QPushButton("📐 Матн ва печатни жойлаш")
        arrange.setToolTip("Текстлар, расм, имзо ва печатни суриш/размерлаш")
        arrange.clicked.connect(self._arrange)
        blank_row.addWidget(arrange)
        root.addLayout(blank_row)

        stamp_row = QHBoxLayout()
        self._stamp_state = QLabel("")
        stamp_row.addWidget(self._stamp_state, stretch=1)
        set_stamp = QPushButton("⚙ Печать юклаш")
        set_stamp.setToolTip("Бир марта юкланади — оқ фони ўзи шаффоф бўлади")
        set_stamp.clicked.connect(self._set_stamp)
        stamp_row.addWidget(set_stamp)
        drop_stamp = QPushButton("🗑 Печать")
        drop_stamp.clicked.connect(self._remove_stamp)
        stamp_row.addWidget(drop_stamp)
        root.addLayout(stamp_row)

        # -- the three pictures ----------------------------------------
        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        self._passport.changed.connect(self._on_dropped)
        docs.addWidget(self._passport)
        self._patent = DropZone("🩷", "Патент (русча ФИО учун)")
        self._patent.changed.connect(self._on_dropped)
        docs.addWidget(self._patent)
        self._photo = DropZone("📷", "Ишчининг ўз расми")
        docs.addWidget(self._photo)
        root.addLayout(docs)

        # what was read, for the operator to check before printing
        from src.ui.widgets.passport_review import PassportReview
        self._review = PassportReview()
        root.addWidget(self._review)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(400)
        self._settle.timeout.connect(self._read_now)

        # -- inputs -----------------------------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)

        grid.addWidget(QLabel("Берилган сана:"), 0, 0)
        self._from = QDateEdit(QDate.currentDate())
        self._from.setCalendarPopup(True)
        self._from.setDisplayFormat("dd.MM.yyyy")
        self._from.dateChanged.connect(self._show_until)
        grid.addWidget(self._from, 0, 1)
        grid.addWidget(QLabel("Амал қилади (ўзи +3 йил):"), 0, 2)
        self._until = QLabel("")
        grid.addWidget(self._until, 0, 3)

        grid.addWidget(QLabel("УДОСТОВЕРЕНИЕ № (1-саҳифа):"), 1, 0)
        self._ud_number = QLineEdit()
        self._ud_number.setPlaceholderText("масалан 440144")
        grid.addWidget(self._ud_number, 1, 1)
        grid.addWidget(QLabel("Бланка рақами (2-саҳифа, ўзи ошади):"), 1, 2)
        self._blank_number = QLineEdit()
        grid.addWidget(self._blank_number, 1, 3)

        # -- signature --------------------------------------------------
        sign_row = QHBoxLayout()
        sign = QPushButton("✍ Имзо қўйиш (ишчи)")
        sign.clicked.connect(self._sign)
        sign_row.addWidget(sign)
        self._sign_state = QLabel("Имзо: ҳали қўйилмаган ⚠️")
        sign_row.addWidget(self._sign_state)
        sign_row.addStretch(1)
        root.addLayout(sign_row)

        # -- run --------------------------------------------------------
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
        self._show_until()

    # ------------------------------------------------------------- state
    def _show_until(self) -> None:
        until = self._c.until(self._from.date().toPython())
        self._until.setText(f"{until:%d.%m.%Y}" if until else "")

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
        self._blank_number.setText(str(self._c.next_number()))

    # ------------------------------------------------------------ blanks
    def _add_template(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "2 саҳифали бланкани танланг", "", "Бланка (*.pdf)")
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
        self._status.setText("✅ Печать сақланди — жойини «📐» билан "
                             "суриш ва размерлаш мумкин.")

    def _remove_stamp(self) -> None:
        self._c.remove_stamp()
        self._reload()

    # ----------------------------------------------------------- arrange
    def _arrange(self) -> None:
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани танланг ёки юкланг.")
            return
        import fitz

        from src.pdf.alpinist_renderer import AlpinistData, values
        from src.pdf.alpinist_spec import IMG_LABELS, IMG_SLOTS, SLOTS
        from src.ui.widgets.layout_editor import Item
        from src.ui.widgets.multipage_layout_editor import MultiPageLayoutEditor

        template = Path(template)
        try:
            pages = []
            with fitz.open(str(template)) as doc:
                for page in doc:
                    pages.append(page.get_pixmap(dpi=110).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        from datetime import date

        sample = values(AlpinistData(
            surname="БАРАТОВ", name="ОЙБЕК", patronymic="БАХРИДДИНОВИЧ",
            ud_number="440144", blank_number=self._blank_number.text() or "145",
            issue_date=date(2026, 5, 10)))
        moved = (self._c.layout(template) or {}).get("fields") or {}
        items_by_page: dict[int, list[Item]] = {}
        for key, slot in {**SLOTS, **IMG_SLOTS}.items():
            if slot.page > len(pages):
                continue
            x, baseline, size = slot.x, slot.baseline, slot.size
            if key in moved and len(moved[key]) == 3:
                x, baseline, size = (float(v) for v in moved[key])
            items_by_page.setdefault(slot.page, []).append(
                Item(key=key, label=key,
                     sample=IMG_LABELS.get(key) or sample.get(key) or key,
                     x=x, baseline=baseline, size=size,
                     font_family="Times New Roman"))
        dialog = MultiPageLayoutEditor(pages, items_by_page,
                                       title="АЛПИНИСТ", parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.save_layout(template, {"fields": dialog.result().items})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText("✅ Матн ва расмларнинг жойлари сақланди.")

    # --------------------------------------------------------- signature
    def _sign(self) -> None:
        from src.ui.widgets.signature_pad import SignaturePad

        pad = SignaturePad(self)
        if pad.exec() != pad.DialogCode.Accepted:
            return
        self._signature = pad.signature_png()
        self._sign_state.setText(
            "Имзо: қўйилди ✅" if self._signature
            else "Имзо: ҳали қўйилмаган ⚠️")

    # ---------------------------------------------------------- printing
    # ------------------------------------------------------------ reading
    def _on_dropped(self) -> None:
        """Passport landed — read after a settle (with the patent if present,
        for the Russian ФИО)."""
        if self._passport.path is None or not self._c.ai_available():
            return
        self._settle.start()

    def _read_now(self) -> None:
        if self._passport.path is None or not self._c.ai_available():
            return
        passport = self._c.read_image(self._passport.path)
        patent = (self._c.read_image(self._patent.path)
                  if self._patent.path is not None else None)
        self._status.setText("⏳ Ҳужжатлар ўқиляпти…")
        self._progress.start("Ҳужжатлар ўқиляпти…")
        run_async(self._c.read_documents, passport, patent,
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

    # ------------------------------------------------------------ printing
    def _generate(self) -> None:
        template = self._template.currentData()
        if not template:
            self._warn("Аввал бланкани юкланг.")
            return
        if self._review.isHidden():
            self._warn("Паспорт расмини ташланг — ўқилсин.")
            return
        if not self._review.has_surname():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return
        if self._photo.path is None:
            self._warn("Ишчининг ўз расмини ташланг.")
            return
        if self._signature is None:
            self._warn("Ишчи аввал «✍ Имзо қўйиш» билан имзо қўйсин.")
            return

        photo = Path(self._photo.path).read_bytes()
        issue_date = self._from.date().toPython()
        ud_number = self._ud_number.text().strip()
        blank_number = self._blank_number.text().strip()
        signature = self._signature

        self._run.setEnabled(False)
        self._progress.start("Карта тайёрланаяпти…")
        run_async(
            self._c.generate,
            template=Path(template), passport=self._review.edited(),
            issue_date=issue_date, ud_number=ud_number,
            blank_number=blank_number, photo=photo, signature=signature,
            on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._passport.clear()
        self._patent.clear()
        self._photo.clear()
        self._review.reset()
        self._signature = None
        self._sign_state.setText("Имзо: ҳали қўйилмаган ⚠️")
        self._reload()
        self._status.setText(f"✅ Тайёр: {result.saved}")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "alpinist"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
