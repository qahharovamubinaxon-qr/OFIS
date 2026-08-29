"""Регистрация screen — «Уведомление о прибытии».

Top: address picker (+ add new address) + registration-expiry date.
Upload passport + patent (front/back) → RUN. The address block and host ФИО are
pre-printed on each address's template; the program fills only the worker boxes
and the two expiry dates. Generation runs on a worker thread.
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
from src.controllers.registration_controller import RegistrationController
from src.domain.registration_address import RegistrationAddress
from src.services.registration_address_service import RegistrationAddressService
from src.services.registration_service import RegistrationResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)

#: Everything the «Уведомление о прибытии» prints off the worker's documents,
#: so any of it can be corrected before it goes onto a filed form. The name
#: and citizenship are read off the patent when there is one (it prints them
#: in Russian), the rest off the passport — but by the time they are in these
#: boxes they are just the values, and the boxes are the single source RUN
#: prints from.
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


_MAIN_FIELDS = [
    ("label", "Nomi (ro'yxatda ko'rinadi, masalan: ПАРКОВАЯ 55)"),
    ("internal_code", "Kod (unikal, masalan: parkovaya55)"),
]

# The 10-field address table (owner's numbering). Program prints these onto the
# blank «Уведомление о прибытии» to make this address's template.
_ADDR_FIELDS = [
    ("oblast", "1 · Область (субъект РФ, masalan: Г МОСКВА)"),
    ("raion", "2 · Район (поселение)"),
    ("gorod", "3 · Город (населенный пункт)"),
    ("ulitsa", "4 · Улица"),
    ("dom", "5 · Дом"),
    ("korpus", "6 · Корпус"),
    ("stroenie", "7 · Строение"),
    ("kvartira", "8 · Квартира"),
    ("host_fio", "9 · Хозяин / Владелец (ФИО)"),
    ("regional_number", "10 · Региональный номер (02/770-…)"),
]


class AddAddressDialog(QDialog):
    """New address: fill the 10-field table (template built from the blank
    automatically) — or upload a ready-made pre-filled template instead."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yangi manzil / Новый адрес")
        self.setMinimumWidth(560)
        self._template: Path | None = None

        outer = QVBoxLayout(self)
        form = QFormLayout()
        self._edits: dict[str, QLineEdit] = {}
        for key, label in _MAIN_FIELDS + _ADDR_FIELDS:
            e = QLineEdit()
            form.addRow(label, e)
            self._edits[key] = e
        outer.addLayout(form)

        hint = QLabel(
            "Jadvalni to'ldirsangiz — shablon avtomatik yasaladi (Times New Roman).\n"
            "Yoki tayyor to'ldirilgan shablon PDF yuklang (jadval shart emas):"
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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _pick_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Registratsiya shabloni PDF", "", "PDF (*.pdf)")
        if path:
            self._template = Path(path)
            self._tpl_label.setText(f"✓ {Path(path).name}")

    def build(self) -> tuple[RegistrationAddress, Path | None]:
        v = {k: e.text().strip() for k, e in self._edits.items()}
        summary = ", ".join(
            x for x in (
                v["oblast"], v["raion"], v["gorod"], v["ulitsa"],
                f"д. {v['dom']}" if v["dom"] else "",
                f"к. {v['korpus']}" if v["korpus"] else "",
                f"стр. {v['stroenie']}" if v["stroenie"] else "",
                f"кв. {v['kvartira']}" if v["kvartira"] else "",
            ) if x
        )
        address = RegistrationAddress(
            label=v["label"] or summary or "Manzil",
            internal_code=v["internal_code"] or "addr",
            address_text=summary or "-",
            host_fio=v["host_fio"] or "-",
            oblast=v["oblast"] or None, raion=v["raion"] or None,
            gorod=v["gorod"] or None, ulitsa=v["ulitsa"] or None,
            dom=v["dom"] or None, korpus=v["korpus"] or None,
            stroenie=v["stroenie"] or None, kvartira=v["kvartira"] or None,
            regional_number=v["regional_number"] or None,
            template_path=self._template or Path("missing.pdf"),
        )
        return address, self._template


class RegistrationView(QWidget):
    def __init__(
        self, controller: RegistrationController, addresses: RegistrationAddressService
    ) -> None:
        super().__init__()
        self._c = controller
        self._addresses_service = addresses

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("Ro'yxatga olish / Регистрация")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- address + registration expiry ------------------------------
        row = QHBoxLayout()
        self._address = QComboBox()
        self._reload_addresses()
        row.addWidget(QLabel("Manzil:"))
        row.addWidget(self._address, stretch=2)

        add = QPushButton("+ Yangi manzil")
        add.clicked.connect(self._add_address)
        arrange = QPushButton("📐 Матнларни жойлаш")
        arrange.setToolTip("Бланка ва унга ёзиладиган маълумотлар экранга "
                           "чиқади — сичқонча билан суриб, катта-кичик қилиб "
                           "жойига қўйинг. Шу бланка учун сақланиб қолади.")
        arrange.clicked.connect(self._arrange)
        row.addWidget(arrange)
        row.addWidget(add)
        rm = QPushButton("🗑")
        rm.setToolTip("Tanlangan manzilni ro'yxatdan o'chirish")
        rm.setFixedWidth(40)
        rm.clicked.connect(self._remove_address)
        row.addWidget(rm)

        self._expiry = QDateEdit()
        self._expiry.setDisplayFormat("dd.MM.yyyy")
        self._expiry.setDate(QDate.currentDate().addDays(90))
        self._expiry.setCalendarPopup(True)
        row.addWidget(QLabel("Ro'yxat tugashi:"))
        row.addWidget(self._expiry)
        root.addLayout(row)

        # -- uploads ----------------------------------------------------
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
        # misread patent went straight onto a filed form. Everything the form
        # prints off the documents is shown here first, and editable.
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
        root.addWidget(self._read)

        # coalesces several drops into one read
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(_SETTLE_MS)
        self._settle.timeout.connect(self._read_now)

        # -- actions ----------------------------------------------------
        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (Регистрация)")
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
        current = self._address.currentText()
        self._reload_addresses()
        idx = self._address.findText(current)
        if idx >= 0:
            self._address.setCurrentIndex(idx)
        self._status.setText(self._hint())

    def _reload_addresses(self) -> None:
        self._address.clear()
        self._addresses = self._c.addresses()
        for a in self._addresses:
            self._address.addItem(a.label)

    def _selected_address(self):
        idx = self._address.currentIndex()
        return self._addresses[idx] if 0 <= idx < len(self._addresses) else None

    def _expiry_date(self) -> date:
        q = self._expiry.date()
        return date(q.year(), q.month(), q.day())

    def _hint(self) -> str:
        if not self._addresses:
            return "Avval «+ Yangi manzil» orqali ro'yxat manzili qo'shing."
        if self._c.ai_available():
            return "AI tayyor. Pasport + patent rasmini yuklab, RUN bosing."
        return "AI kaliti yo'q — Sozlamalarga Gemini kalitini kiriting."

    # ------------------------------------------------------------------

    def _arrange(self) -> None:
        """Drag every printed value into place on THIS blank and keep it."""
        from src.services import registration_service
        from src.ui.widgets.arrange_mapping import arrange

        address = self._selected_address()
        if address is None:
            QMessageBox.information(self, "Diqqat", "Аввал рўйхатдан танланг.")
            return
        if arrange(self, section=registration_service.SECTION,
                   template=address.template_path,
                   mapping_path=registration_service.MAPPING_PATH,
                   title="РЕГИСТРАЦИЯ"):
            QMessageBox.information(
                self, "OK",
                f"«{address.label}» бланкасининг матн жойлари сақланди — "
                "бу манзилга босиладиган ҳар бир ҳужжат шу жойларга тушади.")

    def _add_address(self) -> None:
        dialog = AddAddressDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            address, template = dialog.build()
            has_data = any(
                (address.oblast, address.raion, address.gorod, address.ulitsa,
                 address.dom, address.kvartira)
            )
            if template is None and not has_data:
                QMessageBox.warning(
                    self, "Diqqat",
                    "Manzil jadvalini to'ldiring yoki tayyor shablon PDF tanlang.",
                )
                return
            self._addresses_service.create(
                address, template_source=template, build_from_blank=template is None
            )
            self.refresh()
            QMessageBox.information(self, "OK", f"Manzil qo'shildi: {address.label}")
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
        except Exception as exc:  # noqa: BLE001 - surface validation errors to the user
            QMessageBox.warning(self, "Xato", str(exc))

    def _remove_address(self) -> None:
        address = self._selected_address()
        if address is None:
            return
        if QMessageBox.question(
            self, "O'chirish", f"«{address.label}» ro'yxatdan o'chirilsinmi?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self._addresses_service.archive(address.id)
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
        address = self._selected_address()
        if address is None:
            self._warn("Avval manzil tanlang yoki qo'shing.")
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

        self._busy("Регистрация PDF яратиляпти…")
        run_async(
            self._c.generate, self._edited(), None, address,
            registration_expiry=self._expiry_date(),
            on_success=self._done, on_error=self._failed,
        )

    # ------------------------------------------------------------------
    def _busy(self, msg: str) -> None:
        self._run.setEnabled(False)
        self._status.setText("⏳ " + msg)
        self._progress.start(msg)

    def _done(self, result: RegistrationResult) -> None:
        self._run.setEnabled(True)
        self._progress.finish()
        for dz in (self._dz_passport, self._dz_patent, self._dz_patent_back):
            dz.clear()
        for box in self._boxes.values():
            box.clear()
        self._read.setVisible(False)
        self._status.setText(f"✅ Tayyor: {result.pdf_path.name}")
        from src.ui.widgets.save_to import ask_save_dir

        ask_save_dir(self, [result.pdf_path])
        box = QMessageBox(self)
        box.setWindowTitle("Tayyor")
        box.setText(f"Registratsiya PDF yaratildi:\n{result.pdf_path}")
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
