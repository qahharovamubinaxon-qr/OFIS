"""ХОСТЕЛ screen — arrival notification for hostel-hosted workers.

Same flow as Registration: pick a hostel, upload passport + patent, set the
stay dates → PDF. Hostels are added inline: name, address parts, host ФИО,
organisation name and ИНН — the program prints them onto the bundled hostel
blank (Times New Roman 10) to make that hostel's template, or an already
filled template PDF can be uploaded instead.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.logging import get_logger
from src.common.threading import run_async
from src.controllers.hostel_controller import HostelController
from src.domain.registration_address import RegistrationAddress
from src.services.hostel_service import HostelResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress
from src.ui.widgets.spot_picker import SpotPickerDialog

log = get_logger(__name__)

#: Everything the ХОСТЕЛ «Уведомление о прибытии» prints off the worker's
#: documents, shown for the operator to check before it goes onto a filed form.
#: The name and citizenship come off the patent when there is one (it prints
#: them in Russian), the rest off the passport — but once here they are just the
#: values, and these boxes are the single source RUN prints from.
_READ_BOXES: tuple[tuple[str, str, str], ...] = (
    ("surname", "Фамилия:", "Исоев"),
    ("name", "Имя:", "Аслидин"),
    ("patronymic", "Отчество:", "Холбердиевич"),
    ("citizenship", "Гражданство:", "ТАДЖИКИСТАН"),
    ("series", "Паспорт серия:", "P"),
    ("number", "Паспорт номер:", "405847273"),
    ("issue_date", "Паспорт берилган:", "18.01.2025"),
    ("expiry_date", "Паспорт амал охири:", "17.01.2035"),
)

#: How long to wait after a file lands before reading, so dropping the passport
#: and the patent one after the other reads them together, once.
_SETTLE_MS = 400


def _date_text(when) -> str:
    return when.strftime("%d.%m.%Y") if when else ""


def _date_of(said: str):
    """«18.01.2025» → a date, or nothing when it is not one."""
    from datetime import datetime

    said = (said or "").strip()
    for shape in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(said, shape).date()
        except ValueError:
            continue
    return None


_FIELDS = [
    ("label", "Nomi (ro'yxatda ko'rinadi, masalan: ХОСТЕЛ ЛУЖСКАЯ 10)"),
    ("internal_code", "Kod (unikal, masalan: luzhskaya10)"),
    ("oblast", "Область / субъект РФ (masalan: САНКТ-ПЕТЕРБУРГ Г)"),
    ("raion", "Район / поселение"),
    ("gorod", "Город (населенный пункт)"),
    ("ulitsa", "Улица"),
    ("dom", "Дом"),
    ("korpus", "Корпус"),
    ("stroenie", "Строение / литера"),
    ("komnata", "Комната / помещение"),
    ("host_fio", "Хозяин (ФИО, masalan: ДЯГИЛЕВА ЮЛИЯ ГЕННАДЬЕВНА)"),
    ("organization_name", "Наименование организации"),
    ("inn", "ИНН"),
]


def _spot_text(spot: tuple[float, float] | None) -> str:
    if spot is None:
        return "Boshlanish sanasi: blankaning standart joyida"
    return f"Boshlanish sanasi: belgilangan (x={spot[0]:.0f}, y={spot[1]:.0f})"


def choose_stay_spot(controller: HostelController, parent, *, address=None,
                     template: Path | None = None,
                     current: tuple[float, float] | None = None):
    """Show the page and let the operator mark where the start date goes.

    Returns the new spot, ``None`` for the form's own place, or ``current``
    unchanged when the operator backs out.
    """
    try:
        spot = controller.stay_from_spot(address, template=template, current=current)
    except OfisError as exc:
        QMessageBox.warning(parent, "Xato", exc.message)
        return current
    dialog = SpotPickerDialog(spot, title="Boshlanish sanasi joyi", parent=parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return current
    return dialog.point()


class AddHostelDialog(QDialog):
    def __init__(self, controller: HostelController, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yangi xostel / Новый хостел")
        self.setMinimumWidth(580)
        self._c = controller
        self._template: Path | None = None
        self.spot: tuple[float, float] | None = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        self._edits: dict[str, QLineEdit] = {}
        for key, label in _FIELDS:
            e = QLineEdit()
            form.addRow(label, e)
            self._edits[key] = e
        outer.addLayout(form)

        hint = QLabel(
            "Jadvalni to'ldirsangiz — shablon avtomatik yasaladi (Times New Roman 10).\n"
            "Yoki tayyor to'ldirilgan xostel shabloni PDF yuklang:"
        )
        hint.setStyleSheet("color:#8a94a3;")
        outer.addWidget(hint)

        pick = QHBoxLayout()
        self._tpl_label = QLabel("Tayyor shablon tanlanmagan (ixtiyoriy)")
        btn = QPushButton("Tayyor shablon…")
        btn.clicked.connect(self._pick_template)
        pick.addWidget(self._tpl_label, stretch=1)
        pick.addWidget(btn)
        outer.addLayout(pick)

        spot_row = QHBoxLayout()
        self._spot_label = QLabel("Boshlanish sanasi: blankaning standart joyida")
        spot_btn = QPushButton("Boshlanish sanasi joyi…")
        spot_btn.clicked.connect(self._pick_spot)
        spot_row.addWidget(self._spot_label, stretch=1)
        spot_row.addWidget(spot_btn)
        outer.addLayout(spot_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _pick_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Xostel shabloni PDF", "", "PDF (*.pdf)")
        if path:
            self._template = Path(path)
            self._tpl_label.setText(f"✓ {Path(path).name}")

    def _pick_spot(self) -> None:
        """Mark where this hostel wants the stay-start date, before it exists.

        Against the uploaded template when there is one, otherwise against the
        bundled blank — the box is in the same place on both.
        """
        self.spot = choose_stay_spot(
            self._c, self, template=self._template, current=self.spot)
        self._spot_label.setText(_spot_text(self.spot))

    def build(self) -> tuple[RegistrationAddress, Path | None]:
        v = {k: e.text().strip() for k, e in self._edits.items()}
        summary = ", ".join(
            x for x in (
                v["oblast"], v["raion"], v["gorod"], v["ulitsa"],
                f"д. {v['dom']}" if v["dom"] else "",
                f"к. {v['korpus']}" if v["korpus"] else "",
                f"стр. {v['stroenie']}" if v["stroenie"] else "",
                f"ком. {v['komnata']}" if v["komnata"] else "",
            ) if x
        )
        address = RegistrationAddress(
            label=v["label"] or summary or "Xostel",
            internal_code=v["internal_code"] or "hostel",
            address_text=summary or "-",
            host_fio=v["host_fio"] or "-",
            kind="hostel",
            oblast=v["oblast"] or None, raion=v["raion"] or None,
            gorod=v["gorod"] or None, ulitsa=v["ulitsa"] or None,
            dom=v["dom"] or None, korpus=v["korpus"] or None,
            stroenie=v["stroenie"] or None, komnata=v["komnata"] or None,
            organization_name=v["organization_name"] or None, inn=v["inn"] or None,
            stay_from_x=self.spot[0] if self.spot else None,
            stay_from_y=self.spot[1] if self.spot else None,
            template_path=self._template or Path("missing.pdf"),
        )
        return address, self._template


class HostelView(QWidget):
    def __init__(self, controller: HostelController) -> None:
        super().__init__()
        self._c = controller

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("ХОСТЕЛ — Уведомление о прибытии")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        self._hostel = QComboBox()
        self._reload()
        row.addWidget(QLabel("Xostel:"))
        row.addWidget(self._hostel, stretch=2)

        add = QPushButton("+ Yangi xostel")
        add.clicked.connect(self._add)
        arrange = QPushButton("📐 Матнларни жойлаш")
        arrange.setToolTip("Бланка экранга чиқади — матнларни суриб, "
                           "катта-кичик қилиб, шрифт ва рангини танлаб, "
                           "ўз матнингизни қўшиб жойлайсиз. Имзо ҳам шу "
                           "ерда суриб қўйилади. Шу бланка учун сақланади.")
        arrange.clicked.connect(self._arrange)
        row.addWidget(arrange)
        sign = QPushButton("✒️ Имзо")
        sign.setToolTip("Шу бланкага босиладиган имзо расми — бир марта "
                        "юкланади, кейин «📐» да жойига суриб қўйилади")
        sign.clicked.connect(self._pick_signature)
        row.addWidget(sign)
        row.addWidget(add)
        rm = QPushButton("🗑")
        rm.setToolTip("Tanlangan xostelni ro'yxatdan o'chirish")
        rm.setFixedWidth(40)
        rm.clicked.connect(self._remove)
        row.addWidget(rm)
        restore = QPushButton("↩")
        restore.setToolTip("O'chirilgan xostelni tiklash")
        restore.setFixedWidth(40)
        restore.clicked.connect(self._restore)
        row.addWidget(restore)
        spot = QPushButton("🎯")
        spot.setToolTip("Boshlanish sanasi shu xostelda qayerga chiqsin")
        spot.setFixedWidth(40)
        spot.clicked.connect(self._pick_spot)
        row.addWidget(spot)
        root.addLayout(row)

        dates = QHBoxLayout()
        self._start = QDateEdit()
        self._start.setDisplayFormat("dd.MM.yyyy")
        self._start.setDate(QDate.currentDate())
        self._start.setCalendarPopup(True)
        dates.addWidget(QLabel("Boshlanishi:"))
        dates.addWidget(self._start)
        self._expiry = QDateEdit()
        self._expiry.setDisplayFormat("dd.MM.yyyy")
        self._expiry.setDate(QDate.currentDate().addDays(90))
        self._expiry.setCalendarPopup(True)
        dates.addWidget(QLabel("Tugashi:"))
        dates.addWidget(self._expiry)
        dates.addStretch(1)
        root.addLayout(dates)

        up = QHBoxLayout()
        up.setSpacing(12)
        self._dz_passport = DropZone("🛂", "Паспорт")
        self._dz_patent = DropZone("📄", "Патент (олд)")
        self._dz_patent_back = DropZone("🔄", "Патент (орқа)")
        # dropped and read at once: the operator does not press anything, and
        # every dropped file re-reads after a short settle so the passport and
        # the patent are read together rather than twice
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            dz.changed.connect(self._on_dropped)
            up.addWidget(dz, stretch=1)
        root.addLayout(up)

        # -- what was read, for the operator to check -------------------
        # Reading and printing used to be one press, so a wrong name off a
        # misread patent went straight onto a filed уведомление. Everything the
        # form prints off the documents is shown here first, and editable.
        self._read = QGroupBox("Ҳужжатлардан ўқилгани — текширинг, "
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
        last = len(_READ_BOXES) // 2
        checks.addWidget(QLabel("Жинси:"), last, 0)
        self._gender = QComboBox()
        self._gender.addItems(["Мужской", "Женский"])
        checks.addWidget(self._gender, last, 1)
        checks.addWidget(QLabel("Туғилган сана:"), last, 2)
        self._born = QDateEdit(QDate(2000, 1, 1))
        self._born.setCalendarPopup(True)
        self._born.setDisplayFormat("dd.MM.yyyy")
        checks.addWidget(self._born, last, 3)
        self._read.setVisible(False)
        from src.ui.widgets.shadow import add_shadow
        add_shadow(self._read)
        root.addWidget(self._read)

        # coalesces several drops into one read
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(_SETTLE_MS)
        self._settle.timeout.connect(self._read_now)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (Хостел)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._run_ai)
        actions.addWidget(self._run)
        actions.addStretch(1)
        root.addLayout(actions)

        self._progress = RunProgress()
        root.addWidget(self._progress)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel(self._hint())
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        current = self._hostel.currentText()
        self._reload()
        idx = self._hostel.findText(current)
        if idx >= 0:
            self._hostel.setCurrentIndex(idx)
        self._status.setText(self._hint())

    def _reload(self) -> None:
        self._hostel.clear()
        self._items = self._c.addresses()
        for a in self._items:
            self._hostel.addItem(a.label)

    def _selected(self):
        idx = self._hostel.currentIndex()
        return self._items[idx] if 0 <= idx < len(self._items) else None

    def _expiry_date(self) -> date:
        q = self._expiry.date()
        return date(q.year(), q.month(), q.day())

    def _start_date(self) -> date:
        q = self._start.date()
        return date(q.year(), q.month(), q.day())

    def _hint(self) -> str:
        if not self._items:
            return "Xostel qo'shilmagan — «+ Yangi xostel» tugmasini bosing."
        if self._c.ai_available():
            return "AI tayyor. Pasport + patent rasmlarini yuklang."
        return "AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting."

    # ------------------------------------------------------------------
    def _pick_spot(self) -> None:
        """Move the stay-start date for the hostel already in the picker."""
        address = self._selected()
        if address is None:
            self._warn("Avval xostel tanlang.")
            return
        current = (None if address.stay_from_x is None or address.stay_from_y is None
                   else (address.stay_from_x, address.stay_from_y))
        spot = choose_stay_spot(self._c, self, address=address, current=current)
        if spot == current:
            return
        try:
            self._c.set_stay_from(address.id, spot)
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        self.refresh()
        QMessageBox.information(self, "Saqlandi", _spot_text(spot)
                                + f"\n«{address.label}» uchun eslab qolindi.")


    def _pick_signature(self) -> None:
        """The signature this hostel's papers carry — uploaded once.

        Kept with the BLANK, not with the worker: it is the same signature on
        every уведомление that goes out on that form, and asking for it with
        each one would be a click a day for nothing.
        """
        from src.services import blank_layout, hostel_service

        address = self._selected()
        if address is None:
            QMessageBox.information(self, "Diqqat", "Аввал рўйхатдан танланг.")
            return
        section = hostel_service.SECTION
        have = blank_layout.mark_file(section, address.template_path,
                                      "signature")
        if have is not None:
            asked = QMessageBox.question(
                self, "Имзо",
                f"«{address.label}» да имзо бор ({have.name}).\n"
                "Янгисини юкласизми? «Йўқ» — эскисини ўчиради.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel)
            if asked == QMessageBox.StandardButton.Cancel:
                return
            if asked == QMessageBox.StandardButton.No:
                blank_layout.clear_mark(section, address.template_path,
                                        "signature")
                QMessageBox.information(self, "OK", "Имзо ўчирилди.")
                return
        source, _ = QFileDialog.getOpenFileName(
            self, "Имзо расми", "", "Расм (*.png *.jpg *.jpeg)")
        if not source:
            return
        try:
            blank_layout.set_mark(section, address.template_path, "signature",
                                  Path(source))
        except Exception as exc:                       # noqa: BLE001
            QMessageBox.warning(self, "Xato", str(exc))
            return
        QMessageBox.information(
            self, "OK", "Имзо юкланди — энди «📐 Матнларни жойлаш» да уни "
                        "жойига суриб қўйинг.")

    def _arrange(self) -> None:
        """Drag every printed value into place on THIS blank and keep it."""
        from src.services import hostel_service
        from src.ui.widgets.arrange_mapping import arrange

        address = self._selected()
        if address is None:
            QMessageBox.information(self, "Diqqat", "Аввал рўйхатдан танланг.")
            return
        if arrange(self, section=hostel_service.SECTION,
                   template=address.template_path,
                   mapping_path=hostel_service._hostel_dir() / "mapping.v1.json",
                   title="ХОСТЕЛ", rich=True):
            QMessageBox.information(
                self, "OK",
                f"«{address.label}» бланкасининг матн жойлари сақланди — "
                "бу манзилга босиладиган ҳар бир ҳужжат шу жойларга тушади.")

    def _add(self) -> None:
        dialog = AddHostelDialog(self._c, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        address, template = dialog.build()
        try:
            self._c.add_address(address, template)
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        except Exception as exc:  # noqa: BLE001 - surface to the user
            QMessageBox.warning(self, "Xato", str(exc))
            return
        self.refresh()
        self._hostel.setCurrentIndex(self._hostel.count() - 1)

    def _restore(self) -> None:
        """Bring back a hostel that was removed by accident. The row is still
        in the database — removal only hides it."""
        archived = self._c.archived_addresses()
        if not archived:
            QMessageBox.information(
                self, "Tiklash",
                "O'chirilgan xostel yo'q.\n\nAgar xostelingiz ro'yxatda "
                "ko'rinmasa va bu yerda ham bo'lmasa — bazaning o'zi "
                "almashgan bo'lishi mumkin: Sozlamalar → Zaxira → "
                "«Zaxiradan tiklash».")
            return
        labels = [a.label for a in archived]
        choice, ok = QInputDialog.getItem(
            self, "Tiklash", "Qaysi xostel tiklansin?", labels, 0, False)
        if not ok:
            return
        address = archived[labels.index(choice)]
        try:
            self._c.restore_address(address.id)
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        self.refresh()
        idx = self._hostel.findText(address.label)
        if idx >= 0:
            self._hostel.setCurrentIndex(idx)
        QMessageBox.information(self, "OK", f"«{address.label}» tiklandi.")

    def _remove(self) -> None:
        address = self._selected()
        if address is None:
            return
        confirm = QMessageBox.question(
            self, "O'chirish", f"«{address.label}» ro'yxatdan olinsinmi?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._c.archive_address(address.id)
        self.refresh()

    # ------------------------------------------------------------ reading
    def _on_dropped(self) -> None:
        """A file landed — read after a short settle, so the passport and the
        patent dropped one after the other are read together, once."""
        if self._dz_passport.path is None or not self._c.ai_available():
            return
        self._settle.start()

    def _read_now(self) -> None:
        if self._dz_passport.path is None or not self._c.ai_available():
            return
        passport = self._c.read_image(self._dz_passport.path)
        patent = (self._c.read_image(self._dz_patent.path)
                  if self._dz_patent.path else None)
        patent_back = (self._c.read_image(self._dz_patent_back.path)
                       if self._dz_patent_back.path else None)
        self._status.setText("⏳ Ҳужжатлар ўқиляпти…")
        self._progress.start("Ҳужжатлар ўқиляпти…")
        run_async(self._c.read_documents, passport, patent, patent_back,
                  on_success=self._filled, on_error=self._read_failed)

    def _filled(self, pair) -> None:
        """Show what was read: the patent's name if there was one, else the
        passport's — resolved the same way the printed form resolves it."""
        from src.domain.enums import Gender

        self._progress.finish()
        passport, patent = pair
        resolved = {
            "surname": (patent.holder_surname if patent else None) or passport.surname,
            "name": (patent.holder_name if patent else None) or passport.name,
            "patronymic": (patent.holder_patronymic if patent else None)
            or passport.patronymic or "",
            "citizenship": (patent.holder_citizenship if patent else None)
            or passport.nationality or "",
            "series": passport.series or "",
            "number": passport.number or "",
            "issue_date": _date_text(passport.issue_date),
            "expiry_date": _date_text(passport.expiry_date),
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
        self._status.setText("✅ Ўқилди — текширинг, хатоси бўлса тўғриланг, "
                             "кейин RUN.")

    def _read_failed(self, error: Exception) -> None:
        self._progress.finish()
        self._read.setVisible(True)          # so it can be typed by hand
        msg = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText(f"❌ Ўқилмади: {msg}. Қўлда ёзинг.")

    def _edited(self):
        """The worker as it stands IN THE BOXES — never as it was read.

        A single Passport carries every value the form needs, so patent is
        None at print time: the patent's job was only to supply a Russian name
        when the passport had none, and that name is already in the boxes.
        """
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
            series=said.get("series") or None,
            number=said.get("number") or "—",
            issue_date=_date_of(said.get("issue_date", "")),
            expiry_date=_date_of(said.get("expiry_date", "")),
        )

    # ------------------------------------------------------------ printing
    def _run_ai(self) -> None:
        address = self._selected()
        if address is None:
            self._warn("Avval xostel tanlang yoki qo'shing.")
            return
        # isHidden(), not isVisible(): the read block is revealed with
        # setVisible(True), which clears the hidden flag whether or not the
        # window itself has been shown — so the guard reads the same on screen
        # and under test.
        if self._dz_passport.path is None and self._read.isHidden():
            self._warn("Pasport rasmini yuklang.")
            return
        if self._read.isHidden():
            self._warn("Ҳужжат ҳали ўқилмади — бир оз кутинг.")
            return
        if not self._boxes["surname"].text().strip():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return

        self._busy("Хостел PDF яратиляпти…")
        run_async(
            self._c.generate, self._edited(), None, address,
            registration_expiry=self._expiry_date(),
            registration_start=self._start_date(),
            on_success=self._done, on_error=self._failed,
        )

    # ------------------------------------------------------------------
    def _busy(self, msg: str) -> None:
        self._run.setEnabled(False)
        self._status.setText("⏳ " + msg)
        self._progress.start(msg)

    def _done(self, result: HostelResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            dz.clear()
        for box in self._boxes.values():
            box.clear()
        self._read.setVisible(False)
        from src.ui.widgets.save_to import ask_save_dir

        saved = ask_save_dir(self, [result.pdf_path])
        extra = f" → {saved}" if saved else ""
        self._status.setText(f"✅ Tayyor: {result.pdf_path.name}{extra}")
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"Xostel PDF yaratildi:\n{result.pdf_path}")
        open_btn = box.addButton("Papkani ochish", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("OK", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._open_folder(result.pdf_path.parent)

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        msg = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + msg)
        self._warn(msg)

    def _warn(self, msg: str) -> None:
        QMessageBox.warning(self, "Diqqat", msg)

    @staticmethod
    def _open_folder(folder: Path) -> None:
        import subprocess
        import sys

        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(folder)])  # noqa: S603,S607
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603,S607
        except OSError:
            pass
