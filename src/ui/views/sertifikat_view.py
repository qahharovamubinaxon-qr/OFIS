"""СЕРТИФИКАТ screen — учебный центр «СФЕРА»'s Russian-language certificate.

Drop the student's passport, check the three name fields it gave, pick the city
and the day it was issued, and print. The Latin line under the name, the end
date three years out and both numbers all look after themselves; every one of
them is still shown before printing, and every one can be corrected — the
centre is the one signing the certificate, not the program.
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
from src.controllers.sertifikat_controller import SertifikatController
from src.pdf.sertifikat_renderer import cyrillic_line, latin_line, valid_until
from src.services.sertifikat_service import CITIES, desktop_target
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


def _desktop() -> Path:
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.exists():
            return candidate
    return Path.home()


class SertifikatView(QWidget):
    def __init__(self, controller: SertifikatController) -> None:
        super().__init__()
        self._c = controller
        self._last_pdf: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("СЕРТИФИКАТ — рус тили сертификати (УЦ «СФЕРА»)")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        self._passport = DropZone("🛂", "Ўқувчининг ПАСПОРТИ")
        self._passport.changed.connect(self._on_passport)
        root.addWidget(self._passport)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self._surname = self._line(grid, 0, 0, "Фамилия:")
        self._name = self._line(grid, 0, 2, "Имя:")
        self._patronymic = self._line(grid, 1, 0, "Отчество:")
        for edit in (self._surname, self._name, self._patronymic):
            edit.textChanged.connect(self._show_lines)
        grid.addWidget(QLabel("Город:"), 1, 2)
        self._city = QComboBox()
        self._city.setEditable(True)
        self._city.addItems(CITIES)
        grid.addWidget(self._city, 1, 3)
        root.addLayout(grid)

        # what the certificate will actually carry, on its two lines
        self._lines = QLabel()
        self._lines.setObjectName("cardSubtitle")
        self._lines.setWordWrap(True)
        root.addWidget(self._lines)

        dates = QHBoxLayout()
        dates.addWidget(QLabel("Дата выдачи:"))
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

        numbers = QHBoxLayout()
        numbers.addWidget(QLabel("Регистрационный №:"))
        self._reg = QLineEdit()
        self._reg.setFixedWidth(140)
        numbers.addWidget(self._reg)
        numbers.addWidget(QLabel("Штрих рақами:"))
        self._barcode = QLineEdit()
        self._barcode.setFixedWidth(150)
        numbers.addWidget(self._barcode)
        numbers.addWidget(QLabel("Шаблон:"))
        self._template = QComboBox()
        numbers.addWidget(self._template, stretch=1)
        add = QPushButton("➕ Шаблон қўшиш")
        add.clicked.connect(self._add_template)
        numbers.addWidget(add)
        root.addLayout(numbers)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (СЕРТИФИКАТ PDF)")
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
            "Паспортни ташланг — Ф.И.О. ўзи ўқилади, тагидаги лотинча қатор "
            "ўзи ёзилади. Тугаш санаси 3 йил − 1 кун, регистрационный № ва "
            "штрих рақамининг охирги 3 хонаси ҳар сафар ўзи алмашади. "
            "PDF 2 саҳифа (1-си бўш) бўлиб Рабочий столга ўқувчининг "
            "фамилияси билан сақланади.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

        self._reload_templates()
        self._reload_numbers()
        self._city.setCurrentText(self._c.city())
        self._show_until()
        self._show_lines()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _line(grid: QGridLayout, row: int, col: int, label: str) -> QLineEdit:
        grid.addWidget(QLabel(label), row, col)
        edit = QLineEdit()
        grid.addWidget(edit, row, col + 1)
        return edit

    def _show_until(self) -> None:
        until = valid_until(self._from.date().toPython())
        self._until.setText(
            f"срок действия до {until.strftime('%d.%m.%Y')}  (3 йил − 1 кун)")

    def _show_lines(self) -> None:
        """Show the two lines the certificate will carry, before it is printed."""
        cyrillic = cyrillic_line(self._surname.text(), self._name.text(),
                                 self._patronymic.text())
        latin = latin_line(self._surname.text(), self._name.text())
        self._lines.setText(f"Бланкага ёзилади:   {cyrillic}   /   {latin}"
                            if cyrillic else "")

    def _reload_numbers(self) -> None:
        reg, barcode = self._c.blocks()
        self._reg.setText(reg)
        self._barcode.setText(barcode)

    def _reload_templates(self) -> None:
        self._template.clear()
        for folder in self._c.templates():
            self._template.addItem(folder.name, str(folder))

    def _add_template(self) -> None:
        first, _ = QFileDialog.getOpenFileName(
            self, "1-саҳифа — орқа фон (ёзилмайди)", str(_desktop()), "PDF (*.pdf)")
        if not first:
            return
        second, _ = QFileDialog.getOpenFileName(
            self, "2-саҳифа — тўлдириладиган юз", str(_desktop()), "PDF (*.pdf)")
        if not second:
            return
        name, ok = QInputDialog.getText(self, "Шаблон номи", "Ном:")
        if not ok or not name.strip():
            return
        try:
            dest = self._c.add_template(name, Path(first), Path(second))
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
        missing = [title for title, key in
                   (("Фамилия", "surname"), ("Имя", "name")) if not fields[key]]
        self._status.setText(
            "✅ Паспорт ўқилди — текшириб RUN босинг."
            + (f"  ⚠️ Ўқилмади: {', '.join(missing)} — қўлда киритинг."
               if missing else ""))

    # ----------------------------------------------------------- printing
    def _generate(self) -> None:
        template = self._template.currentData()
        try:
            result = self._c.generate(
                surname=self._surname.text(), name=self._name.text(),
                patronymic=self._patronymic.text(),
                city=self._city.currentText(),
                issued_on=self._from.date().toPython(),
                reg_number=self._reg.text(), barcode_number=self._barcode.text(),
                template=Path(template) if template else None)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        target = desktop_target(result.filename)
        target.write_bytes(result.pdf)
        self._last_pdf = target
        self._open.setEnabled(True)
        self._status.setText(
            f"✅ Рабочий столга сақланди: {target.name}\n"
            f"Регистрационный № {result.reg_number} · штрих "
            f"{result.barcode_number} · {result.issued_on:%d.%m.%Y} — "
            f"{result.valid_until:%d.%m.%Y}")

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
        """A new student — the city and the number blocks stay, the name goes."""
        self._passport.clear()
        for edit in (self._surname, self._name, self._patronymic):
            edit.clear()
        self._last_pdf = None
        self._open.setEnabled(False)
        self._reload_numbers()
        self._show_lines()
