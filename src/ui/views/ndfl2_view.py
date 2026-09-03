"""2 НДФЛ — «Справка о доходах и суммах налога физического лица».

Passport and patent in, the twelve month boxes filled in as far as the
worker was paid, and the справка comes out on the firm's own sheet: the
program totals the months, carries the total into «Общая сумма дохода» and
«Налоговая база», and works the 13% tax out for both tax rows.

Every printed value can be dragged, resized, recoloured and set in any
installed font in ONE window, and the office may add texts of its own.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.ndfl2_controller import Ndfl2Controller
from src.pdf.ndfl2_renderer import money
from src.pdf.ndfl2_spec import ALL_SLOTS, BOLD, FAMILY, TAX_RATE
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

_MONTHS = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль",
           "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")


def _amount(text: str) -> Decimal | None:
    """«150 000,50» / «150000.5» / «150000» → Decimal, or None if empty."""
    cleaned = (text or "").replace(" ", "").replace("\xa0", "")
    cleaned = cleaned.replace("₽", "").replace(",", ".").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value > 0 else None


class Ndfl2View(QWidget):
    def __init__(self, controller: Ndfl2Controller) -> None:
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

        title = QLabel("2 НДФЛ — справка о доходах")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        firm_row = QHBoxLayout()
        firm_row.addWidget(QLabel("Фирма:"))
        self._firm = QComboBox()
        firm_row.addWidget(self._firm, stretch=1)
        add = QPushButton("➕ Фирма (бланка юклаш)")
        add.setToolTip("Фирманинг ўз бўш справкаси — реквизит, имзо, печать "
                       "билан; программа фақат ишчини ёзади")
        add.clicked.connect(self._add_firm)
        firm_row.addWidget(add)
        drop = QPushButton("🗑")
        drop.clicked.connect(self._remove_firm)
        firm_row.addWidget(drop)
        arrange = QPushButton("📐 Созлаш")
        arrange.setToolTip("Матнларни суриш, катта-кичик қилиш, ранг ва "
                           "шрифт танлаш, матн қўшиш")
        arrange.clicked.connect(self._arrange)
        firm_row.addWidget(arrange)
        root.addLayout(firm_row)

        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        self._passport.changed.connect(self._on_dropped)
        docs.addWidget(self._passport)
        self._patent = DropZone("🩷", "Патент (ИНН учун)")
        self._patent.changed.connect(self._on_dropped)
        docs.addWidget(self._patent)
        root.addLayout(docs)

        # what was read, for the operator to check before printing
        from src.ui.widgets.passport_review import PassportReview
        self._review = PassportReview()
        root.addWidget(self._review)
        self._inn = ""            # read off the patent, kept for the справка
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(400)
        self._settle.timeout.connect(self._read_now)

        head = QGridLayout()
        head.setHorizontalSpacing(10)
        root.addLayout(head)
        head.addWidget(QLabel("Справка санаси:"), 0, 0)
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd.MM.yyyy")
        head.addWidget(self._date, 0, 1)
        head.addWidget(QLabel("Қайси йил учун:"), 0, 2)
        self._year = QSpinBox()
        self._year.setRange(2000, 2100)
        self._year.setValue(QDate.currentDate().year())
        head.addWidget(self._year, 0, 3)

        root.addWidget(QLabel(
            "Ойликлар — нечта ойни тўлдирсангиз, ўшанча ой ёзилади:"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        root.addLayout(grid)
        self._months: list[QLineEdit] = []
        for index, name in enumerate(_MONTHS):
            row, column = index % 6, index // 6
            grid.addWidget(QLabel(f"{index + 1}. {name}"), row, column * 2)
            edit = QLineEdit()
            edit.setPlaceholderText("масалан 150000")
            edit.textChanged.connect(self._show_totals)
            grid.addWidget(edit, row, column * 2 + 1)
            self._months.append(edit)

        self._totals = QLabel("")
        self._totals.setWordWrap(True)
        self._totals.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._totals)

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
        self._show_totals()

    # ------------------------------------------------------------- state
    def _reload(self) -> None:
        current = self._firm.currentData()
        self._firm.clear()
        for firm in self._c.firms():
            self._firm.addItem(firm.name, str(firm))
        if self._firm.count() == 0:
            self._firm.addItem("— фирма йўқ, «➕ Фирма» —", None)
        elif current:
            index = self._firm.findData(current)
            if index >= 0:
                self._firm.setCurrentIndex(index)

    def _months_typed(self) -> dict[int, Decimal]:
        found: dict[int, Decimal] = {}
        for index, edit in enumerate(self._months, start=1):
            value = _amount(edit.text())
            if value is not None:
                found[index] = value
        return found

    def _show_totals(self) -> None:
        months = self._months_typed()
        total = sum(months.values(), Decimal("0"))
        tax = (total * Decimal(str(TAX_RATE))).quantize(Decimal("0.01"))
        self._totals.setText(
            f"Тўлдирилган ой: {len(months)} · Общая сумма дохода: "
            f"{money(total)} · Налоговая база: {money(total)} · "
            f"Сумма налога (13%): {money(tax)}")

    def _selected(self) -> Path | None:
        chosen = self._firm.currentData()
        return Path(chosen) if chosen else None

    # ------------------------------------------------------------- firms
    def _add_firm(self) -> None:
        name, ok = QInputDialog.getText(self, "Янги фирма", "Фирма номи:")
        if not ok or not name.strip():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Фирманинг бўш 2НДФЛ бланкаси (PDF)", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            made = self._c.add_firm(name.strip(), Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        index = self._firm.findData(str(made))
        if index >= 0:
            self._firm.setCurrentIndex(index)
        self._status.setText(f"✅ «{made.name}» қўшилди — «📐 Созлаш» билан "
                             "жойларини текширинг.")

    def _remove_firm(self) -> None:
        firm = self._selected()
        if firm is None:
            return
        if QMessageBox.question(self, "Ўчириш",
                                f"«{firm.name}» ўчирилсинми?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_firm(firm)
        self._reload()

    # ----------------------------------------------------------- arrange
    def _arrange(self) -> None:
        firm = self._selected()
        if firm is None:
            self._warn("Аввал фирмани танланг.")
            return
        import fitz

        from src.pdf.ndfl2_renderer import placed
        from src.pdf.trud8_fields import Field
        from src.ui.widgets.field_editor import FieldEditor

        blank = self._c.blank(firm)
        if blank is None:
            self._warn("Бу фирмада бланка йўқ.")
            return
        try:
            with fitz.open(str(blank)) as doc:
                pages = [p.get_pixmap(dpi=100).tobytes("png") for p in doc]
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        layout = self._c.layout(firm)
        styles = layout.get("styles") or {}
        slots = placed(layout)
        catalogue = {key: slot.label or key for key, slot in ALL_SLOTS.items()}
        samples = {key: slot.sample for key, slot in ALL_SLOTS.items()}
        frozen = set(ALL_SLOTS)
        from src.pdf.ndfl2_renderer import anchor_offset

        fields = []
        for key, slot in slots.items():
            chosen = styles.get(key) or {}
            # the editor drags by the LEFT edge; a right-aligned or centred
            # value is anchored elsewhere, so it is converted both ways
            offset = anchor_offset(ALL_SLOTS[key], slot.size)
            fields.append(Field(
                key=key, page=1, x=slot.x - offset, baseline=slot.baseline,
                size=slot.size,
                colour=tuple(chosen.get("colour") or (0.0, 0.0, 0.0))[:3],
                font=str(chosen.get("font") or FAMILY),
                bold=bool(chosen.get("bold", BOLD))))
        for index, extra in enumerate(layout.get("extra") or []):
            key = f"extra{index}"
            catalogue[key] = f"Қўшимча матн {index + 1}"
            samples[key] = str(extra.get("text") or "матн")
            fields.append(Field(
                key=key, page=1, x=float(extra.get("x", 0.1)),
                baseline=float(extra.get("baseline", 0.1)),
                size=float(extra.get("size", 0.0116)),
                colour=tuple(extra.get("colour") or (0.0, 0.0, 0.0))[:3],
                font=str(extra.get("font") or FAMILY),
                bold=bool(extra.get("bold", BOLD))))

        dialog = FieldEditor(pages, fields, title=firm.name, parent=self,
                             catalogue=catalogue, samples=samples,
                             frozen=frozen)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        new_fields: dict[str, list[float]] = {}
        new_styles: dict[str, dict] = {}
        new_extra: list[dict] = []
        for made in dialog.fields():
            if made.key in ALL_SLOTS:
                new_fields[made.key] = [round(made.x, 5),
                                        round(made.baseline, 5),
                                        round(made.size, 5)]
                new_styles[made.key] = {"font": made.font,
                                        "bold": made.bold,
                                        "colour": list(made.colour),
                                        "size": round(made.size, 5)}
            else:
                new_extra.append({
                    "text": samples.get(made.key, "матн"),
                    "x": round(made.x, 5), "baseline": round(made.baseline, 5),
                    "size": round(made.size, 5), "font": made.font,
                    "bold": made.bold, "colour": list(made.colour)})
        self._c.save_layout(firm, {"fields": new_fields, "styles": new_styles,
                                   "extra": new_extra})
        self._status.setText("✅ Жойлар ва созламалар сақланди.")

    # ---------------------------------------------------------- printing
    # ----------------------------------------------------------- reading
    def _on_dropped(self) -> None:
        """A document landed — read after a short settle."""
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

    def _filled(self, triple) -> None:
        self._progress.finish()
        passport, patent, inn = triple
        self._inn = inn                       # the патент's ИНН, for the справка
        self._review.fill(passport, patent)
        self._status.setText("✅ Ўқилди — текширинг, хатоси бўлса тўғриланг, "
                             "кейин Тайёрлаш.")

    def _read_failed(self, error: Exception) -> None:
        self._progress.finish()
        self._review.reveal()          # so it can be typed by hand
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ Ўқилмади: {message}. Қўлда ёзинг.")

    # ----------------------------------------------------------- printing
    def _generate(self) -> None:
        firm = self._selected()
        if firm is None:
            self._warn("Аввал фирмани танланг.")
            return
        if self._passport.path is None and self._review.isHidden():
            self._warn("Паспорт расмини ташланг.")
            return
        if self._review.isHidden():
            self._warn("Ҳужжат ҳали ўқилмади — бир оз кутинг.")
            return
        if not self._review.has_surname():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return
        months = self._months_typed()
        if not months:
            self._warn("Камида битта ойнинг ойлигини киритинг.")
            return
        when: date = self._date.date().toPython()
        year = self._year.value()

        self._run.setEnabled(False)
        self._progress.start("Справка тайёрланаяпти…")
        run_async(
            self._c.generate, firm, self._review.edited(),
            months=months, year=year, form_date=when, inn=self._inn,
            on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._passport.clear()
        self._patent.clear()
        self._review.reset()
        self._inn = ""
        self._status.setText(
            f"✅ Тайёр: {result.pdf_path.name} · жами {money(result.total)} · "
            f"солиқ {money(result.tax)}")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "ndfl2"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        for edit in self._months:
            edit.clear()
