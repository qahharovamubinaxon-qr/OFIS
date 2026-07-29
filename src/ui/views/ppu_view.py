"""ППУ screen — the pair the office prints from a worker's регистрация.

Drop the регистрация and the worker's photograph, check the fields the
регистрация gave, type the day it starts, and print. Both sheets are saved to
the desktop as pictures under the worker's surname.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QImage, QPixmap
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
from src.controllers.ppu_controller import PpuController
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


def _desktop() -> Path:
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.exists():
            return candidate
    return Path.home()


class PpuView(QWidget):
    def __init__(self, controller: PpuController) -> None:
        super().__init__()
        self._c = controller
        self._last: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("ППУ — ишчининг ППУ жуфтлиги")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        zones = QHBoxLayout()
        self._reg = DropZone("🏠", "РЕГИСТРАЦИЯ расми")
        self._reg.changed.connect(self._on_registration)
        zones.addWidget(self._reg, stretch=1)
        self._photo = DropZone("🖼️", "Ишчининг РАСМИ")
        zones.addWidget(self._photo, stretch=1)
        root.addLayout(zones)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self._surname = self._line(grid, 0, 0, "Фамилия:")
        self._name = self._line(grid, 0, 2, "Имя:")
        self._patronymic = self._line(grid, 1, 0, "Отчество:")
        self._birth = self._line(grid, 1, 2, "Дата рождения:")
        self._birth.setPlaceholderText("03.03.1977")
        self._gender = self._line(grid, 2, 0, "Пол:")
        self._gender.setPlaceholderText("Мужской")
        self._citizenship = self._line(grid, 2, 2, "Гражданство:")
        self._document = self._line(grid, 3, 0, "Паспорт (серия/номер):")
        self._document.setToolTip(
            "«Иностранный паспорт» — олд бетнинг пастига ва орқа бетнинг "
            "тепасидаги тўртта жойга, беш марта ёзилади.")
        self._address = self._line(grid, 4, 0, "Адрес:")
        grid.addWidget(self._address, 4, 1, 1, 3)
        root.addLayout(grid)

        dates = QHBoxLayout()
        dates.addWidget(QLabel("Срок с:"))
        self._from = QDateEdit()
        self._from.setDisplayFormat("dd.MM.yyyy")
        self._from.setDate(QDate.currentDate())
        self._from.setCalendarPopup(True)
        dates.addWidget(self._from)
        dates.addWidget(QLabel("по:"))
        self._to = QDateEdit()
        self._to.setDisplayFormat("dd.MM.yyyy")
        self._to.setDate(QDate.currentDate().addDays(90))
        self._to.setCalendarPopup(True)
        self._to.setToolTip("Регистрациядан ўқилади — керак бўлса тузатинг.")
        dates.addWidget(self._to)
        dates.addWidget(QLabel("Шаблон:"))
        self._template = QComboBox()
        dates.addWidget(self._template, stretch=1)
        add = QPushButton("➕ Шаблон қўшиш")
        add.clicked.connect(self._add_template)
        dates.addWidget(add)
        root.addLayout(dates)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (ППУ)")
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

        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(200)
        root.addWidget(self._preview, stretch=1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        self._status = QLabel(
            "Регистрация ва ишчининг расмини ташланг — Ф.И.О., туғилган "
            "сана, фуқаролик, паспорт, адрес ва тугаш санаси регистрациядан "
            "ўқилади. Бошланиш санасини ўзингиз киритасиз. Икки саҳифа расм "
            "ҳолида Рабочий столга сақланади.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

        self._reload_templates()

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
            self._template.addItem("— бланка юкланмаган —", None)

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

    # ------------------------------------------------------- registration
    def _on_registration(self) -> None:
        if self._reg.path is None:
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        data = Path(self._reg.path).read_bytes()
        self._status.setText("⏳ Регистрация ўқилаяпти…")
        self._progress.start("Регистрациядан маълумот олинаяпти…")
        run_async(self._c.read_registration, data,
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, fields: dict[str, str]) -> None:
        self._progress.finish()
        for edit, key in ((self._surname, "surname"), (self._name, "name"),
                          (self._patronymic, "patronymic"),
                          (self._gender, "gender"),
                          (self._citizenship, "citizenship"),
                          (self._document, "document"),
                          (self._address, "address")):
            if fields.get(key):
                edit.setText(fields[key])
        for text, box in ((fields.get("birth_date", ""), self._birth),
                          (None, None)):
            if text and box is not None:
                parsed = self._c.parse_date(text)
                box.setText(parsed.strftime("%d.%m.%Y") if parsed else text)
        for key, box in (("stay_from", self._from), ("stay_to", self._to)):
            parsed = self._c.parse_date(fields.get(key, ""))
            if parsed:
                box.setDate(QDate(parsed.year, parsed.month, parsed.day))
        missing = [t for t, k in (("Фамилия", "surname"), ("адрес", "address"),
                                  ("тугаш санаси", "stay_to"))
                   if not fields.get(k)]
        self._status.setText(
            "✅ Регистрация ўқилди — текшириб RUN босинг."
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
                gender=self._gender.text(),
                citizenship=self._citizenship.text(),
                document=self._document.text(),
                address=self._address.text(),
                valid_from=self._from.date().toPython(),
                valid_to=self._to.date().toPython(),
                photo=photo,
                template=Path(template) if template else None)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        self._last = result.saved[0] if result.saved else None
        self._open.setEnabled(bool(result.saved))
        if result.pages:
            pix = QPixmap.fromImage(QImage.fromData(result.pages[0], "PNG"))
            self._preview.setPixmap(pix.scaledToHeight(
                max(160, self._preview.height()),
                Qt.TransformationMode.SmoothTransformation))
        warning = ("\n⚠️ Расм юкланмади — ППУ расмсиз чиқди."
                   if self._photo.path is None else "")
        names = ", ".join(p.name for p in result.saved)
        self._status.setText(
            f"✅ Рабочий столга сақланди: {names}\n"
            f"{result.passport} · {result.valid_from:%d.%m.%Y} — "
            f"{result.valid_to:%d.%m.%Y}" + warning)

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
        """A new worker — the blank number and the template stay."""
        self._reg.clear()
        self._photo.clear()
        for edit in (self._surname, self._name, self._patronymic, self._birth,
                     self._gender, self._citizenship, self._document,
                     self._address):
            edit.clear()
        self._preview.clear()
        self._last = None
        self._open.setEnabled(False)
