"""СНИЛС screen — «Ишчининг СНИЛС номери».

Drop the passport, check the fields it gave, set the registration date, and
print. The СНИЛС number stays in its box between workers; type over it when it
changes. Blanks can be added and removed from here.
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
from src.controllers.snils_controller import SnilsController
from src.services.snils_service import desktop_target
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


def _desktop() -> Path:
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.exists():
            return candidate
    return Path.home()


class SnilsView(QWidget):
    def __init__(self, controller: SnilsController) -> None:
        super().__init__()
        self._c = controller
        self._last: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("СНИЛС — ишчининг СНИЛС номери")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        self._passport = DropZone("🛂", "Ишчининг ПАСПОРТИ")
        self._passport.changed.connect(self._on_passport)
        root.addWidget(self._passport)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self._surname = self._line(grid, 0, 0, "Фамилия:")
        self._name = self._line(grid, 0, 2, "Имя:")
        self._patronymic = self._line(grid, 1, 0, "Отчество:")
        self._birth = self._line(grid, 1, 2, "Дата рождения:")
        self._birth.setPlaceholderText("25.06.1997")
        self._place = self._line(grid, 2, 0, "Место рождения:")
        self._place.setPlaceholderText("КИРГИЗИЯ")
        self._gender = self._line(grid, 2, 2, "Пол:")
        self._gender.setPlaceholderText("ЖЕНСКИЙ")
        root.addLayout(grid)

        row = QHBoxLayout()
        row.addWidget(QLabel("СНИЛС №:"))
        self._snils = QLineEdit()
        self._snils.setFixedWidth(200)
        self._snils.setToolTip(
            "Бўш қолдирсангиз — қутидаги рақам ёзилади.\n"
            "Янгисини ёзсангиз — ўшаниси ёзилади ва эсда қолади.")
        row.addWidget(self._snils)
        row.addWidget(QLabel("Дата регистрации:"))
        self._reg = QDateEdit()
        self._reg.setDisplayFormat("dd.MM.yyyy")
        self._reg.setDate(QDate.currentDate())
        self._reg.setCalendarPopup(True)
        row.addWidget(self._reg)
        row.addStretch(1)
        root.addLayout(row)

        blanks = QHBoxLayout()
        blanks.addWidget(QLabel("Бланка:"))
        self._template = QComboBox()
        blanks.addWidget(self._template, stretch=1)
        add = QPushButton("➕ Бланка қўшиш")
        add.clicked.connect(self._add_template)
        blanks.addWidget(add)
        self._drop = QPushButton("🗑 Бланкани ўчириш")
        self._drop.clicked.connect(self._remove_template)
        blanks.addWidget(self._drop)
        root.addLayout(blanks)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (СНИЛС PDF)")
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
            "Паспортни ташланг — Ф.И.О., туғилган сана, туғилган жойи "
            "(давлат) ва жинси ўзи ўқилади. СНИЛС рақами қутида туради, "
            "янгисини ёзсангиз ўшаниси ёзилади. PDF Рабочий столга "
            "фамилия билан сақланади.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)
        root.addStretch(1)

        self._reload_templates()
        self._snils.setText(self._c.number())

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _line(grid: QGridLayout, row: int, col: int, label: str) -> QLineEdit:
        grid.addWidget(QLabel(label), row, col)
        edit = QLineEdit()
        grid.addWidget(edit, row, col + 1)
        return edit

    def _reload_templates(self) -> None:
        self._template.clear()
        for folder in self._c.templates():
            self._template.addItem(folder.name, str(folder))
        if not self._template.count():
            self._template.addItem("— бланка йўқ —", None)
        self._drop.setEnabled(self._template.count() > 1)

    def _add_template(self) -> None:
        blank, _ = QFileDialog.getOpenFileName(
            self, "СНИЛС бланкаси (PDF)", str(_desktop()), "PDF (*.pdf)")
        if not blank:
            return
        name, ok = QInputDialog.getText(self, "Бланка номи", "Ном:")
        if not ok or not name.strip():
            return
        try:
            dest = self._c.add_template(name, Path(blank))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload_templates()
        self._template.setCurrentIndex(self._template.findData(str(dest)))
        self._status.setText(f"✅ Бланка қўшилди: {dest.name}")

    def _remove_template(self) -> None:
        folder = self._template.currentData()
        if not folder:
            return
        name = self._template.currentText()
        if QMessageBox.question(
                self, "Ўчириш",
                f"«{name}» бланкаси ўчирилсинми?\nБу қайтарилмайди.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self._c.remove_template(Path(folder))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload_templates()
        self._status.setText(f"🗑 Ўчирилди: {name}")

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
        for edit, key in ((self._surname, "surname"), (self._name, "name"),
                          (self._patronymic, "patronymic"),
                          (self._birth, "birth_date"),
                          (self._place, "birth_place"),
                          (self._gender, "gender")):
            if fields.get(key):
                edit.setText(fields[key])
        missing = [t for t, k in (("Фамилия", "surname"), ("Имя", "name"),
                                  ("туғилган сана", "birth_date"))
                   if not fields.get(k)]
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
                birth_date=self._c.parse_date(self._birth.text()),
                birth_place=self._place.text(), gender=self._gender.text(),
                reg_date=self._reg.date().toPython(),
                snils=self._snils.text(),
                template=Path(template) if template else None)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        target = desktop_target(result.filename)
        target.write_bytes(result.pdf)
        self._last = target
        self._open.setEnabled(True)
        self._snils.setText(result.snils)
        self._status.setText(
            f"✅ Рабочий столга сақланди: {target.name}\n"
            f"СНИЛС {result.snils} · {result.reg_date:%d.%m.%Y}")

    def _failed(self, error: Exception) -> None:
        self._run.setEnabled(True)
        self._progress.fail()
        message = error.message if isinstance(error, OfisError) else str(error)
        self._status.setText("❌ " + message)
        QMessageBox.warning(self, "Xato", message)

    def _open_folder(self) -> None:
        if self._last is None:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last.parent)))

    def _warn(self, message: str) -> None:
        self._status.setText("⚠️ " + message)
        QMessageBox.information(self, "Diqqat", message)

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        """A new worker — the СНИЛС number and the blank stay."""
        self._passport.clear()
        for edit in (self._surname, self._name, self._patronymic,
                     self._birth, self._place, self._gender):
            edit.clear()
        self._last = None
        self._open.setEnabled(False)
