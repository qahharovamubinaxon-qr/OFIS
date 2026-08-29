"""КАРТА ИНОСТРАННОГО ГРАЖДАНИНА — passport + photo in, the card out."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.threading import run_async
from src.controllers.karta_controller import KartaController
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

#: Everything the card prints off the passport, so any of it can be corrected
#: before it is laminated onto a card that is hard to remake.
_READ_BOXES: tuple[tuple[str, str, str], ...] = (
    ("surname", "Фамилия:", "Исоев"),
    ("name", "Имя:", "Аслидин"),
    ("patronymic", "Отчество:", "Холбердиевич"),
    ("citizenship", "Гражданство:", "ТАДЖИКИСТАН"),
)
_SETTLE_MS = 400


class KartaView(QWidget):
    def __init__(self, controller: KartaController) -> None:
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

        title = QLabel("КАРТА ИНОСТРАННОГО ГРАЖДАНИНА")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        blanks = QHBoxLayout()
        self._blank_state = QLabel("")
        self._blank_state.setWordWrap(True)
        blanks.addWidget(self._blank_state, stretch=1)
        add_inner = QPushButton("➕ Ички")
        add_inner.setToolTip("Ички томон бланкаси (маълумотлар ёзиладиган)")
        add_inner.clicked.connect(lambda: self._set_blank("inner"))
        blanks.addWidget(add_inner)
        add_outer = QPushButton("➕ Ташқи")
        add_outer.setToolTip("Ташқи томон — фақат карта рақами ёзилади")
        add_outer.clicked.connect(lambda: self._set_blank("outer"))
        blanks.addWidget(add_outer)
        arrange = QPushButton("📐 Матнларни жойлаш")
        arrange.clicked.connect(self._arrange)
        blanks.addWidget(arrange)
        style = QPushButton("🎨 Ранг ва қалинлик")
        style.setToolTip("Ҳар матннинг рангини ва жирний/оддийлигини танлаш")
        style.clicked.connect(self._style)
        blanks.addWidget(style)
        root.addLayout(blanks)

        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        # dropped and read at once — the worker's data is shown for checking
        # before it is printed onto a laminated card
        self._passport.changed.connect(self._on_dropped)
        docs.addWidget(self._passport)
        self._photo = DropZone("📷", "Ишчининг расми")
        docs.addWidget(self._photo)
        root.addLayout(docs)

        # -- what was read, for the operator to check --------------------
        self._read = QGroupBox("Паспортдан ўқилгани — текширинг, "
                               "хатоси бўлса тўғриланг")
        checks = QGridLayout(self._read)
        checks.setHorizontalSpacing(10)
        checks.setVerticalSpacing(6)
        self._boxes: dict[str, QLineEdit] = {}
        for at, (key, label, hint) in enumerate(_READ_BOXES):
            box = QLineEdit()
            box.setPlaceholderText(hint)
            checks.addWidget(QLabel(label), at // 2, (at % 2) * 2)
            checks.addWidget(box, at // 2, (at % 2) * 2 + 1)
            self._boxes[key] = box
        row2 = len(_READ_BOXES) // 2
        checks.addWidget(QLabel("Жинси:"), row2, 0)
        self._gender = QComboBox()
        self._gender.addItems(["Мужской", "Женский"])
        checks.addWidget(self._gender, row2, 1)
        checks.addWidget(QLabel("Туғилган сана:"), row2, 2)
        self._born = QDateEdit(QDate(2000, 1, 1))
        self._born.setCalendarPopup(True)
        self._born.setDisplayFormat("dd.MM.yyyy")
        checks.addWidget(self._born, row2, 3)
        self._read.setVisible(False)
        root.addWidget(self._read)

        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(_SETTLE_MS)
        self._settle.timeout.connect(self._read_now)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)
        grid.addWidget(QLabel("Берилган сана:"), 0, 0)
        self._from = QDateEdit(QDate.currentDate())
        self._from.setCalendarPopup(True)
        self._from.setDisplayFormat("dd.MM.yyyy")
        self._from.dateChanged.connect(self._show_expiry)
        grid.addWidget(self._from, 0, 1)
        grid.addWidget(QLabel("Тугаши (ўзи +5 йил):"), 0, 2)
        self._expiry = QLabel("")
        grid.addWidget(self._expiry, 0, 3)

        grid.addWidget(QLabel("Карта рақами (АА1234567):"), 1, 0)
        self._code = QLineEdit()
        self._code.setPlaceholderText("масалан АВ1563244")
        grid.addWidget(self._code, 1, 1)
        self._numbers = QLabel("")
        self._numbers.setWordWrap(True)
        grid.addWidget(self._numbers, 1, 2, 1, 2)

        sign_row = QHBoxLayout()
        sign = QPushButton("✍ Имзо қўйиш (ишчи)")
        sign.clicked.connect(self._sign)
        sign_row.addWidget(sign)
        self._sign_state = QLabel("Имзо: ҳали қўйилмаган (ихтиёрий)")
        sign_row.addWidget(self._sign_state)
        sign_row.addStretch(1)
        root.addLayout(sign_row)

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
        self._show_expiry()

    # ------------------------------------------------------------- state
    def _show_expiry(self) -> None:
        made = self._c.expiry(self._from.date().toPython())
        self._expiry.setText(f"{made:%d.%m.%Y}" if made else "")

    def _reload(self) -> None:
        inner = self._c.blank("inner")
        outer = self._c.blank("outer")
        self._blank_state.setText(
            f"Ички: {'✅ ' + inner.name if inner else '⚠️ юкланмаган'}   ·   "
            f"Ташқи: {'✅ ' + outer.name if outer else '— йўқ'}")
        numbers = self._c.next_numbers()
        self._numbers.setText(
            f"Кейинги рақамлар (ўзи ошади): {numbers['serial']} · "
            f"{numbers['card_number']} · 06/30 {numbers['series']}")

    # ------------------------------------------------------------ blanks
    def _set_blank(self, side: str) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, f"{'Ички' if side == 'inner' else 'Ташқи'} бланка", "",
            "Бланка (*.pdf *.jpg *.jpeg *.png)")
        if not source:
            return
        try:
            self._c.set_blank(side, Path(source))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._status.setText("✅ Бланка юкланди.")

    # ----------------------------------------------------------- arrange
    def _sample(self):
        from datetime import date as _date

        from src.pdf.karta_renderer import KartaData

        numbers = self._c.next_numbers()
        return KartaData(
            surname="МАМАТОВ", name="ФАЙЗУЛЛОХОН", patronymic="МАМАТОВИЧ",
            gender="male", citizenship="УЗБЕКИСТАН",
            birth_date=_date(1975, 4, 15), issued=_date(2026, 5, 20),
            expiry=_date(2031, 5, 20), card_code="AA5675223",
            serial=numbers["serial"], card_number=numbers["card_number"],
            series=numbers["series"])

    def _arrange(self) -> None:
        inner = self._c.blank("inner")
        if inner is None:
            self._warn("Аввал ички бланкани юкланг.")
            return
        import fitz

        from src.pdf.karta_renderer import placed, values
        from src.ui.widgets.layout_editor import Item
        from src.ui.widgets.multipage_layout_editor import MultiPageLayoutEditor

        outer = self._c.blank("outer")
        pages = []
        try:
            for path in (p for p in (inner, outer) if p is not None):
                with fitz.open(str(path)) as raw:
                    doc = (raw if raw.is_pdf
                           else fitz.open("pdf", raw.convert_to_pdf()))
                    pages.append(doc[0].get_pixmap(dpi=110).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        sample = values(self._sample())
        slots = placed(self._c.layout())
        items_by_page: dict[int, list[Item]] = {}
        for key, slot in slots.items():
            if slot.page > len(pages):
                continue
            items_by_page.setdefault(slot.page, []).append(
                Item(key=key, label=key, sample=sample.get(key) or key,
                     x=slot.x, baseline=slot.baseline, size=slot.size,
                     colour=slot.colour,
                     font_family="Courier New" if slot.mono else "Arial"))
        dialog = MultiPageLayoutEditor(pages, items_by_page,
                                       title="КАРТА", parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.save_layout({"fields": dialog.result().items})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText("✅ Матн жойлари сақланди.")

    def _style(self) -> None:
        """Colour and weight, per text — kept beside the blank."""
        from src.pdf.karta_renderer import placed

        inner = self._c.blank("inner")
        if inner is None:
            self._warn("Аввал ички бланкани юкланг.")
            return
        keys = list(placed(self._c.layout()))
        picked, ok = _pick_item(self, "Қайси матн?", keys)
        if not ok:
            return
        slot = placed(self._c.layout())[picked]
        colour = QColorDialog.getColor(parent=self, title="Матн ранги")
        if not colour.isValid():
            return
        weight, ok = _pick_item(self, "Қалинлиги", ["Жирний (bold)", "Оддий"])
        if not ok:
            return
        kept = self._c.layout()
        styles = dict(kept.get("styles") or {})
        styles[picked] = {
            "colour": [colour.redF(), colour.greenF(), colour.blueF()],
            "bold": weight.startswith("Жирний")}
        try:
            self._c.save_layout({"styles": styles})
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(
            f"✅ «{picked}» — ранг ва қалинлик сақланди "
            f"({'жирний' if styles[picked]['bold'] else 'оддий'}). "
            f"Аввалгиси: {'жирний' if slot.bold else 'оддий'}.")

    # --------------------------------------------------------- signature
    def _sign(self) -> None:
        from src.ui.widgets.signature_pad import SignaturePad

        pad = SignaturePad(self)
        # the card's signature is BLACK, not the алпинист's ink
        pad.set_ink((0, 0, 0))
        if pad.exec() != pad.DialogCode.Accepted:
            return
        self._signature = pad.signature_png()
        self._sign_state.setText(
            "Имзо: қўйилди ✅" if self._signature
            else "Имзо: ҳали қўйилмаган (ихтиёрий)")

    # ------------------------------------------------------------ reading
    def _on_dropped(self) -> None:
        if self._passport.path is None or not self._c.ai_available():
            return
        self._settle.start()

    def _read_now(self) -> None:
        if self._passport.path is None or not self._c.ai_available():
            return
        data = Path(self._passport.path).read_bytes()
        self._status.setText("⏳ Паспорт ўқилаяпти…")
        self._progress.start("Паспорт ўқилаяпти…")
        run_async(self._c.read_passport, data,
                  on_success=self._filled, on_error=self._read_failed)

    def _filled(self, passport) -> None:
        from src.domain.enums import Gender

        self._progress.finish()
        resolved = {
            "surname": passport.surname or "",
            "name": passport.name or "",
            "patronymic": passport.patronymic or "",
            "citizenship": passport.nationality or "",
        }
        for key, box in self._boxes.items():
            box.setText(str(resolved.get(key, "")))
        self._gender.setCurrentText(
            "Женский" if passport.gender == Gender.FEMALE else "Мужской")
        if passport.birth_date:
            self._born.setDate(QDate(passport.birth_date.year,
                                     passport.birth_date.month,
                                     passport.birth_date.day))
        self._read.setVisible(True)
        self._status.setText("✅ Ўқилди — текширинг, кейин Тайёрлаш.")

    def _read_failed(self, error: Exception) -> None:
        self._progress.finish()
        self._read.setVisible(True)          # so it can be typed by hand
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText(f"❌ Ўқилмади: {message}. Қўлда ёзинг.")

    def _edited(self):
        """The worker as it stands IN THE BOXES — never as it was read."""
        from src.domain.documents import Passport
        from src.domain.enums import Gender

        said = {key: box.text().strip() for key, box in self._boxes.items()}
        return Passport(
            surname=said.get("surname") or "—",
            name=said.get("name") or "—",
            patronymic=said.get("patronymic") or None,
            gender=(Gender.FEMALE if self._gender.currentText() == "Женский"
                    else Gender.MALE),
            birth_date=self._born.date().toPython(),
            nationality=said.get("citizenship") or None,
            number="—")

    # ---------------------------------------------------------- printing
    def _generate(self) -> None:
        if self._c.blank("inner") is None:
            self._warn("Аввал ички бланкани юкланг.")
            return
        if self._passport.path is None and self._read.isHidden():
            self._warn("Паспорт расмини ташланг.")
            return
        if self._photo.path is None:
            self._warn("Ишчининг расмини ташланг.")
            return
        if not self._code.text().strip():
            self._warn("Карта рақамини киритинг (масалан АВ1563244).")
            return
        if self._read.isHidden():
            self._warn("Паспорт ҳали ўқилмади — бир оз кутинг.")
            return
        if not self._boxes["surname"].text().strip():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return
        photo = Path(self._photo.path).read_bytes()
        issued = self._from.date().toPython()
        code = self._code.text().strip()
        signature = self._signature
        worker = self._edited()

        self._run.setEnabled(False)
        self._progress.start("Карта тайёрланаяпти…")

        def work():
            return self._c.generate(passport=worker, photo=photo,
                                    signature=signature, issued=issued,
                                    card_code=code)

        run_async(work, on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._signature = None
        self._sign_state.setText("Имзо: ҳали қўйилмаган (ихтиёрий)")
        for box in self._boxes.values():
            box.clear()
        self._read.setVisible(False)
        self._reload()
        self._status.setText(f"✅ Тайёр: {result.saved} "
                             f"(№ {result.card_number})")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "karta"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass


def _pick_item(parent, title: str, items: list[str]) -> tuple[str, bool]:
    from PySide6.QtWidgets import QInputDialog

    return QInputDialog.getItem(parent, "КАРТА", title, items, 0, False)
