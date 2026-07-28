"""РАЗРЕШЕНИЯ screen — the work permit card, front and back.

Drop the worker's passport and their photograph, check the five fields the
passport gave, type the job, the day it starts, the worker's ИНН if there is
one, and print. The end date, the two card numbers and the firm all look after
themselves; every one of them is still shown before printing, and every one can
be corrected — the operator is the one signing the card, not the program.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
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
from src.common.threading import run_async
from src.controllers.razreshenie_controller import RazreshenieController
from src.pdf.razreshenie_renderer import cover_until
from src.services.razreshenie_service import desktop_target
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


def _desktop() -> Path:
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.exists():
            return candidate
    return Path.home()


class RazreshenieView(QWidget):
    def __init__(self, controller: RazreshenieController) -> None:
        super().__init__()
        self._c = controller
        self._last_pdf: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("РАЗРЕШЕНИЯ — ишчининг рухсатнома картаси")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        zones = QHBoxLayout()
        self._passport = DropZone("🛂", "Ишчининг ПАСПОРТИ")
        self._passport.changed.connect(self._on_passport)
        zones.addWidget(self._passport, stretch=1)
        self._photo = DropZone("🖼️", "Ишчининг РАСМИ (3×4)")
        zones.addWidget(self._photo, stretch=1)
        root.addLayout(zones)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self._surname = self._line(grid, 0, 0, "Фамилия:")
        self._name = self._line(grid, 0, 2, "Имя:")
        self._patronymic = self._line(grid, 1, 0, "Отчество:")
        self._birth = self._line(grid, 1, 2, "Дата рождения:")
        self._birth.setPlaceholderText("01.09.1976")
        self._citizenship = self._line(grid, 2, 0, "Гражданство:")
        self._document = self._line(grid, 2, 2, "Паспорт (серия/номер):")
        self._inn = self._line(grid, 3, 0, "Ишчининг ИНН:")
        self._inn.setMaxLength(12)
        self._inn.setPlaceholderText("бўш қолса — фақат паспорт ёзилади")
        self._activity = self._line(grid, 3, 2, "Должность:")
        self._activity.setPlaceholderText("Разнорабочий")
        root.addLayout(grid)

        dates = QHBoxLayout()
        dates.addWidget(QLabel("Действительно с:"))
        self._from = QDateEdit()
        self._from.setDisplayFormat("dd.MM.yyyy")
        self._from.setDate(QDate.currentDate())
        self._from.setCalendarPopup(True)
        self._from.dateChanged.connect(self._show_until)
        dates.addWidget(self._from)
        self._until = QLabel()
        self._until.setStyleSheet("font-weight:600;")
        dates.addWidget(self._until)
        dates.addStretch(1)
        root.addLayout(dates)
        self._show_until()

        firm = QHBoxLayout()
        firm.addWidget(QLabel("Фирма:"))
        self._firm_name = QLineEdit()
        firm.addWidget(self._firm_name, stretch=2)
        firm.addWidget(QLabel("ИНН:"))
        self._firm_inn = QLineEdit()
        self._firm_inn.setFixedWidth(140)
        firm.addWidget(self._firm_inn)
        self._firms = QComboBox()
        self._firms.setMinimumWidth(150)
        self._firms.currentIndexChanged.connect(self._pick_firm)
        firm.addWidget(self._firms)
        root.addLayout(firm)

        numbers = QHBoxLayout()
        numbers.addWidget(QLabel("Серия:"))
        self._seria = QLineEdit()
        self._seria.setFixedWidth(70)
        numbers.addWidget(self._seria)
        numbers.addWidget(QLabel("№:"))
        self._number = QLineEdit()
        self._number.setFixedWidth(120)
        numbers.addWidget(self._number)
        numbers.addWidget(QLabel("Орқа ВВ №:"))
        self._back = QLineEdit()
        self._back.setFixedWidth(120)
        numbers.addWidget(self._back)
        numbers.addWidget(QLabel("Шаблон:"))
        self._template = QComboBox()
        numbers.addWidget(self._template, stretch=1)
        add = QPushButton("➕ Шаблон қўшиш")
        add.clicked.connect(self._add_template)
        numbers.addWidget(add)
        root.addLayout(numbers)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (РАЗРЕШЕНИЕ PDF)")
        self._run.setObjectName("runButton")
        self._run.clicked.connect(self._generate)
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
            "Паспортни ташланг — Ф.И.О., туғилган сана, фуқаролик ва паспорт "
            "рақами ўзи ўқилади. Расм рамкага тўлиқ жойлашади. Тугаш санаси, "
            "карта рақамлари ва фирма ўзи тўлади — текшириб RUN босинг. "
            "PDF (олд + орқа) Рабочий столга ишчининг фамилияси билан "
            "сақланади.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

        self._reload_firms()
        self._reload_templates()
        self._reload_numbers()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _line(grid: QGridLayout, row: int, col: int, label: str) -> QLineEdit:
        grid.addWidget(QLabel(label), row, col)
        edit = QLineEdit()
        grid.addWidget(edit, row, col + 1)
        return edit

    def _show_until(self) -> None:
        q = self._from.date()
        until = cover_until(q.toPython())
        self._until.setText(f"по {until.strftime('%d.%m.%Y')}  (1 йил − 1 кун)")

    def _reload_numbers(self) -> None:
        seria, number, back = self._c.next_numbers()
        self._seria.setText(seria)
        self._number.setText(number)
        self._back.setText(back)

    def _reload_firms(self) -> None:
        current = self._c.firm()
        self._firm_name.setText(current.name)
        self._firm_inn.setText(current.inn)
        self._firms.blockSignals(True)
        self._firms.clear()
        self._firms.addItem("— олдинги фирмалар —", None)
        for firm in self._c.firms():
            self._firms.addItem(firm.name[:38], (firm.name, firm.inn))
        self._firms.blockSignals(False)

    def _pick_firm(self) -> None:
        data = self._firms.currentData()
        if data:
            self._firm_name.setText(data[0])
            self._firm_inn.setText(data[1])

    def _reload_templates(self) -> None:
        self._template.clear()
        for folder in self._c.templates():
            self._template.addItem(folder.name, str(folder))

    def _add_template(self) -> None:
        front, _ = QFileDialog.getOpenFileName(
            self, "ОЛД бланка (бўш)", str(_desktop()), "PDF (*.pdf)")
        if not front:
            return
        back, _ = QFileDialog.getOpenFileName(
            self, "ОРҚА бланка (бўш)", str(_desktop()), "PDF (*.pdf)")
        if not back:
            return
        name, ok = QInputDialog.getText(self, "Шаблон номи", "Ном:")
        if not ok or not name.strip():
            return
        try:
            dest = self._c.add_template(name, Path(front), Path(back))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload_templates()
        self._template.setCurrentIndex(self._template.findData(str(dest)))
        self._status.setText(f"✅ Шаблон қўшилди: {dest.name}")

    # ----------------------------------------------------------- passport
    def _on_passport(self) -> None:
        if self._passport.path is None:
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        data = Path(self._passport.path).read_bytes()
        self._status.setText("⏳ Паспорт ўқилаяпти…")
        self._progress.start("Паспортдан маълумот олинаяпти…")
        run_async(self._c.read_passport, data,
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, fields: dict[str, str]) -> None:
        self._progress.finish()
        self._surname.setText(fields["surname"])
        self._name.setText(fields["name"])
        self._patronymic.setText(fields["patronymic"])
        self._birth.setText(fields["birth_date"])
        self._citizenship.setText(fields["citizenship"])
        self._document.setText(fields["document"])
        missing = [title for title, key in
                   (("Фамилия", "surname"), ("Имя", "name"),
                    ("паспорт", "document")) if not fields[key]]
        self._status.setText(
            "✅ Паспорт ўқилди — текшириб RUN босинг."
            + (f"  ⚠️ Ўқилмади: {', '.join(missing)} — қўлда киритинг."
               if missing else ""))

    # ----------------------------------------------------------- printing
    def _generate(self) -> None:
        photo = None
        if self._photo.path is not None:
            photo = Path(self._photo.path).read_bytes()
        template = self._template.currentData()
        try:
            result = self._c.generate(
                surname=self._surname.text(), name=self._name.text(),
                patronymic=self._patronymic.text(),
                birth_date=self._c.parse_date(self._birth.text()),
                citizenship=self._citizenship.text(),
                document=self._document.text(), inn=self._inn.text(),
                activity=self._activity.text(),
                valid_from=self._from.date().toPython(),
                firm_name=self._firm_name.text(), firm_inn=self._firm_inn.text(),
                seria=self._seria.text(), number=self._number.text(),
                back_number=self._back.text(), photo=photo,
                template=Path(template) if template else None)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        # straight to the desktop under the worker's surname — no dialog, the
        # operator prints these one after another and should not be stopped
        target = desktop_target(result.filename)
        target.write_bytes(result.pdf)
        self._last_pdf = target
        self._open.setEnabled(True)
        self._reload_numbers()
        self._reload_firms()
        warning = ("\n⚠️ Расм юкланмади — карта расмсиз чиқди."
                   if self._photo.path is None else "")
        self._status.setText(
            f"✅ Рабочий столга сақланди: {target.name}\n"
            f"{result.seria} № {result.number} · ВВ {result.back_number} · "
            f"{result.valid_from:%d.%m.%Y} — {result.valid_to:%d.%m.%Y}"
            + warning)

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + message)
        QMessageBox.warning(self, "Xato", message)

    def _open_folder(self) -> None:
        if self._last_pdf is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_pdf.parent)))

    def _warn(self, message: str) -> None:
        self._status.setText("⚠️ " + message)
        QMessageBox.information(self, "Diqqat", message)

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        """A new worker — the firm and the numbers stay, everything else goes."""
        self._passport.clear()
        self._photo.clear()
        for edit in (self._surname, self._name, self._patronymic, self._birth,
                     self._citizenship, self._document, self._inn,
                     self._activity):
            edit.clear()
        self._last_pdf = None
        self._open.setEnabled(False)
        self._reload_numbers()
