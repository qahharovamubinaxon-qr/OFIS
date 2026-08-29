"""ИНН screen — the office's own record sheet of a worker's tax number.

Drop the worker's passport (or patent), pick the date, type the twelve digits
of the ИНН → RUN. The sheet is saved as a PDF for the worker's folder.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QTimer
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
from src.controllers.inn_controller import InnController
from src.services.inn_service import INN_DIGITS, InnResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

#: Everything the ИНН sheet prints off the passport, so any of it can be
#: corrected before it goes onto the worker's filed record.
_READ_BOXES: tuple[tuple[str, str, str], ...] = (
    ("surname", "Фамилия:", "Исоев"),
    ("name", "Имя:", "Аслидин"),
    ("patronymic", "Отчество:", "Холбердиевич"),
    ("citizenship", "Гражданство:", "ТАДЖИКИСТАН"),
)
#: How long to wait after a file lands before reading it.
_SETTLE_MS = 400


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


class InnView(QWidget):
    def __init__(self, controller: InnController) -> None:
        super().__init__()
        self._c = controller
        self._result: InnResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ИНН — ишчининг ИНН рақами варағи")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        row = QHBoxLayout()
        row.addWidget(QLabel("Кун:"))
        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        row.addWidget(self._date)
        row.addSpacing(20)
        row.addWidget(QLabel("ИНН рақами:"))
        self._inn = QLineEdit()
        self._inn.setPlaceholderText(f"{INN_DIGITS} та рақам")
        self._inn.setMaxLength(20)
        self._inn.setFixedWidth(200)
        self._inn.textChanged.connect(self._show_count)
        row.addWidget(self._inn)
        self._count = QLabel()
        self._count.setStyleSheet("color:#8a94a3;")
        row.addWidget(self._count)
        row.addStretch(1)
        root.addLayout(row)

        self._dz = DropZone("🛂", "Ишчининг паспорти ёки патенти")
        # dropped and read at once — the worker's ФИО and the ИНН both come
        # off the same photograph, and the operator checks them before RUN
        self._dz.changed.connect(self._on_dropped)
        root.addWidget(self._dz, stretch=1)

        # -- what was read, for the operator to check --------------------
        # The sheet prints the worker's ФИО, sex, birth date and citizenship;
        # they used to be read only inside the print step, so a misread name
        # went onto a filed sheet unseen. Shown here first, and editable.
        self._read = QGroupBox("Ҳужжатдан ўқилгани — текширинг, "
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

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (ИНН)")
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

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel(
            "Паспорт ёки патент расмини юкланг, кунни танланг ва ИНН рақамини "
            "ёзинг. Ф.И.О., жинси, туғилган санаси ва фуқаролиги ҳужжатдан "
            "олинади.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

        self._show_count()

    # ------------------------------------------------------------------
    def _show_count(self) -> None:
        digits = "".join(c for c in self._inn.text() if c.isdigit())
        if not digits:
            self._count.setText("")
        elif len(digits) == INN_DIGITS:
            self._count.setText("✅")
        else:
            self._count.setText(f"{len(digits)}/{INN_DIGITS}")

    def _form_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    # -- the worker and the ИНН, off the dropped document --------------
    def _on_dropped(self) -> None:
        if self._dz.path is None or not self._c.ai_available():
            return
        self._settle.start()

    def _read_now(self) -> None:
        if self._dz.path is None or not self._c.ai_available():
            return
        data = Path(self._dz.path).read_bytes()
        self._status.setText("⏳ Ҳужжат ўқилаяпти…")
        self._progress.start("Ҳужжат ўқилаяпти…")
        run_async(self._c.read_all, data,
                  on_success=self._filled, on_error=self._read_failed)

    def _filled(self, pair) -> None:
        from src.domain.enums import Gender

        self._progress.finish()
        passport, inn_digits = pair
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
        # the ИНН only into an EMPTY box — a number the operator typed wins
        if inn_digits and not "".join(c for c in self._inn.text() if c.isdigit()):
            self._inn.setText(inn_digits)
        self._read.setVisible(True)
        found = "✅ ИНН ҳам топилди — " if inn_digits else "ℹ️ ИНН топилмади, ўзингиз ёзинг. "
        self._status.setText(found + "ўқилганини текширинг, кейин RUN.")

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
            number="—",
        )

    def _run_ai(self) -> None:
        if self._dz.path is None and self._read.isHidden():
            self._warn("Ишчининг паспорти ёки патенти расмини юкланг.")
            return
        if self._read.isHidden():
            self._warn("Ҳужжат ҳали ўқилмади — бир оз кутинг.")
            return
        if not self._boxes["surname"].text().strip():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return
        digits = "".join(c for c in self._inn.text() if c.isdigit())
        if len(digits) != INN_DIGITS:
            self._warn(f"ИНН {INN_DIGITS} та рақамдан иборат бўлиши керак "
                       f"(ҳозир {len(digits)} та).")
            return

        self._run.setEnabled(False)
        self._status.setText("⏳ Варақ тайёрланяпти…")
        self._progress.start("ИНН варағи тайёрланяпти…")
        run_async(self._c.generate, self._edited(),
                  inn=digits, form_date=self._form_date(),
                  on_success=self._done, on_error=self._failed)

    def _done(self, result: InnResult) -> None:
        self._run.setEnabled(True)
        self._open.setEnabled(True)
        self._progress.finish()
        self._result = result
        self._dz.clear()
        self._inn.clear()
        for box in self._boxes.values():
            box.clear()
        self._read.setVisible(False)
        self._status.setText(
            f"✅ {result.surname} — ИНН {result.inn}\n{result.pdf_path}")

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
        self._inn.clear()
        for box in self._boxes.values():
            box.clear()
        self._read.setVisible(False)
        self._result = None
        self._open.setEnabled(False)
        self._show_count()
