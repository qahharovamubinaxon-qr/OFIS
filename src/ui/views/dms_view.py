"""ДМС screen — the office's РЕСО «ДМС-Трудовой» policy for one worker.

Drop the worker's passport, pick the start date, type the phone and the
registration address → RUN. Everything else comes off the passport, the end
date is a year less a day, and the policy number is taken from the block РЕСО
allocated to the agency (Sozlamalar → ДМС).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
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
from src.common.threading import run_async
from src.controllers.dms_controller import DmsController
from src.services.dms_service import DmsResult, policy_end_date
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

#: Everything the policy prints off the passport, so any of it can be
#: corrected before it goes onto a document.
_READ_BOXES: tuple[tuple[str, str, str], ...] = (
    ("surname", "Фамилия:", "Исоев"),
    ("name", "Исм:", "Аслидин"),
    ("patronymic", "Отчество:", "Холбердиевич"),
    ("nationality", "Гражданство:", "Таджикистан"),
    ("series", "Паспорт серия:", "P"),
    ("number", "Паспорт номер:", "405847273"),
    ("issue_date", "Берилган сана:", "18.01.2025"),
    ("issued_by", "Ким берган:", "ХШБ дар Ч.Балхи"),
)


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


class DmsView(QWidget):
    def __init__(self, controller: DmsController) -> None:
        super().__init__()
        self._c = controller
        self._result: DmsResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ДМС — полис «ДМС-Трудовой»")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        self._counter = QLabel()
        self._counter.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._counter)

        # -- dates -------------------------------------------------------
        row = QHBoxLayout()
        row.addWidget(QLabel("Бошланиш санаси:"))
        self._start = QDateEdit()
        self._start.setDisplayFormat("dd.MM.yyyy")
        self._start.setDate(QDate.currentDate())
        self._start.setCalendarPopup(True)
        self._start.dateChanged.connect(self._sync_end)
        row.addWidget(self._start)
        self._end = QLabel()
        self._end.setStyleSheet("font-weight:600;")
        row.addWidget(self._end)
        row.addStretch(1)
        root.addLayout(row)

        # -- typed fields ------------------------------------------------
        fields = QHBoxLayout()
        self._phone = QLineEdit()
        self._phone.setPlaceholderText("+7 968 394-10-08")
        self._address = QLineEdit()
        self._address.setPlaceholderText("Москва, Вяземская улица, 1к1, кв. 62")
        self._region = QLineEdit()
        self._region.setPlaceholderText("Москва")
        self._region.setFixedWidth(140)
        for label, widget, stretch in (("Телефон:", self._phone, 1),
                                       ("Рўйхат манзили:", self._address, 3),
                                       ("Патент ҳудуди:", self._region, 0)):
            fields.addWidget(QLabel(label))
            fields.addWidget(widget, stretch=stretch)
        root.addLayout(fields)

        # -- passport ----------------------------------------------------
        self._dz = DropZone("🛂", "Ишчининг паспортини юкланг")
        # dropped, and read at once: the operator does not have to press
        # anything and can go on typing the address while it works
        self._dz.changed.connect(self._on_dropped)
        root.addWidget(self._dz, stretch=1)

        # -- what was read, for the operator to check --------------------
        # Reading and printing used to be one press, so nobody ever saw what
        # had been read until the policy came out with it on. Everything the
        # policy prints off the passport is shown here first.
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

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (ДМС)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._run_ai)
        actions.addWidget(self._run)
        self._open = QPushButton("📂 Папкани очиш")
        self._open.setEnabled(False)
        self._open.clicked.connect(self._open_folder)
        actions.addWidget(self._open)
        actions.addStretch(1)
        root.addLayout(actions)

        self._progress = RunProgress()
        root.addWidget(self._progress)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(rule)

        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

        self._sync_end()
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        nxt, left = self._c.next_number(), self._c.remaining()
        if nxt:
            self._counter.setText(f"Кейинги полис рақами: {nxt}   ·   қолди: {left} та")
            self._status.setText(
                "Паспортни юкланг, санани танланг, телефон ва манзилни ёзинг.")
        else:
            self._counter.setText("⚠️  Полис рақамлари киритилмаган")
            self._status.setText(
                "Sozlamalar → ДМС бўлимига РЕСО берган рақамлар оралиғини "
                "киритинг — программа фақат ўша оралиқдаги рақамларни ишлатади.")

    def _sync_end(self) -> None:
        q = self._start.date()
        end = policy_end_date(date(q.year(), q.month(), q.day()))
        self._end.setText(f"→  тугаши: {end.strftime('%d.%m.%Y')}")

    def _start_date(self) -> date:
        q = self._start.date()
        return date(q.year(), q.month(), q.day())

    # ------------------------------------------------------------------
    # ------------------------------------------------------------ reading
    def _on_dropped(self) -> None:
        """A passport landed — read it now, without being asked to."""
        if self._dz.path is None or not self._c.ai_available():
            return
        image = Path(self._dz.path).read_bytes()
        self._status.setText("⏳ Паспорт ўқиляпти… (адресни ёзаверинг)")
        self._progress.start("Паспорт ўқиляпти…")
        run_async(self._c.read_passport, image,
                  on_success=self._filled, on_error=self._read_failed)

    def _filled(self, passport) -> None:
        self._progress.finish()
        self._passport = passport
        for key, box in self._boxes.items():
            said = getattr(passport, key, "") or ""
            box.setText(_date_text(said) if hasattr(said, "year") else str(said))
        gender = getattr(passport, "gender", None)
        self._gender.setCurrentText(
            "Женский" if str(getattr(gender, "value", gender) or "").lower()
            .startswith(("f", "ж")) else "Мужской")
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
        self._status.setText(f"❌ Паспорт ўқилмади: {error}. Қўлда ёзинг.")

    def _edited(self):
        """The passport as it stands IN THE BOXES — never as it was read."""
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
            nationality=said.get("nationality") or None,
            series=said.get("series") or None,
            number=said.get("number") or "—",
            issue_date=_date_of(said.get("issue_date", "")),
            issued_by=said.get("issued_by") or None)

    # ------------------------------------------------------------ printing
    def _run_ai(self) -> None:
        if self._dz.path is None and not self._read.isVisible():
            self._warn("Ишчининг паспорт расмини юкланг.")
            return
        if not self._address.text().strip():
            self._warn("Рўйхатдан ўтиш манзилини ёзинг.")
            return
        if not self._c.next_number():
            self._warn("Полис рақами йўқ — Sozlamalar → ДМС бўлимига РЕСО "
                       "берган рақамлар оралиғини киритинг.")
            return
        if not self._read.isVisible():
            self._warn("Паспорт ҳали ўқилмади — бир оз кутинг.")
            return
        if not self._boxes["surname"].text().strip():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return

        self._run.setEnabled(False)
        self._status.setText("⏳ Полис тайёрланяпти…")
        self._progress.start("Полис тайёрланяпти…")
        run_async(
            self._c.generate, self._edited(),
            start_date=self._start_date(),
            phone=self._phone.text().strip(),
            address=self._address.text().strip(),
            region=self._region.text().strip() or None,
            on_success=self._done, on_error=self._failed,
        )

    def _done(self, result: DmsResult) -> None:
        self._run.setEnabled(True)
        self._open.setEnabled(True)
        self._progress.finish()
        self._result = result
        self._dz.clear()
        self.refresh()
        self._status.setText(
            f"✅ Полис № {result.policy_number} тайёр  ·  "
            f"{result.start_date.strftime('%d.%m.%Y')} — "
            f"{result.end_date.strftime('%d.%m.%Y')}\n{result.pdf_path}")

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + message)
        QMessageBox.warning(self, "Xato", message)

    def _open_folder(self) -> None:
        if self._result is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._result.pdf_path.parent)))

    def _warn(self, message: str) -> None:
        self._status.setText("⚠️ " + message)
        QMessageBox.information(self, "Diqqat", message)

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        self._dz.clear()
        self._phone.clear()
        self._address.clear()
        self._result = None
        self._open.setEnabled(False)
        self.refresh()
