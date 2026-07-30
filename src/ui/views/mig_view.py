"""МИГ screen — the «ИШЧИ КАРТАСИ» the office prints for each of its firms.

Drop the worker's passport: the name, birth date, citizenship, sex and passport
number come off it. Type the card's own series and number, the visa if there is
one, tick which of the four jobs the worker holds, and the dates. Pick the
firm's blank and its stamp — the stamp lands where it was put last time.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
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
from src.controllers.mig_controller import MigController
from src.pdf.mig_spec import JOBS
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

_BLANK_FILTER = "Бланка (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
_STAMP_FILTER = "Печат расми (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"


def _desktop() -> Path:
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.exists():
            return candidate
    return Path.home()


class MigView(QWidget):
    def __init__(self, controller: MigController) -> None:
        super().__init__()
        self._c = controller
        self._last: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(10)

        title = QLabel("МИГ — ИШЧИ КАРТАСИ")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        # -- the firm: its blank and its stamp -------------------------
        firm = QHBoxLayout()
        firm.addWidget(QLabel("Бланка:"))
        self._template = QComboBox()
        firm.addWidget(self._template, stretch=1)
        add_blank = QPushButton("➕ Бланка")
        add_blank.setToolTip("Фирманинг бўш ИШЧИ КАРТАСИ — PDF ёки расм")
        add_blank.clicked.connect(self._add_template)
        firm.addWidget(add_blank)
        drop_blank = QPushButton("✕")
        drop_blank.setFixedWidth(28)
        drop_blank.clicked.connect(self._remove_template)
        firm.addWidget(drop_blank)

        firm.addSpacing(12)
        firm.addWidget(QLabel("Печат:"))
        self._stamp = QComboBox()
        firm.addWidget(self._stamp, stretch=1)
        add_stamp = QPushButton("➕ Печат")
        add_stamp.setToolTip("Фирманинг печати — расм (фони шаффоф бўлса яхши)")
        add_stamp.clicked.connect(self._add_stamp)
        firm.addWidget(add_stamp)
        place = QPushButton("🎯 Жойлаш")
        place.setToolTip("Печатни сичқонча билан суриб жойига қўйинг ва "
                         "ўлчамини танланг — шу ҳолида сақланиб қолади")
        place.clicked.connect(self._place_stamp)
        firm.addWidget(place)
        drop_stamp = QPushButton("✕")
        drop_stamp.setFixedWidth(28)
        drop_stamp.clicked.connect(self._remove_stamp)
        firm.addWidget(drop_stamp)
        root.addLayout(firm)

        # -- the passport ----------------------------------------------
        zones = QHBoxLayout()
        self._passport = DropZone("🛂", "ИШЧИНИНГ ПАСПОРТИ")
        self._passport.changed.connect(self._on_passport)
        zones.addWidget(self._passport, stretch=1)
        root.addLayout(zones)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self._surname = self._line(grid, 0, 0, "ФАМИЛИЯ:")
        self._surname_lat = self._line(grid, 0, 2, "Латинча (ўзи ясалади):")
        self._name = self._line(grid, 1, 0, "ИСМИ:")
        self._patronymic = self._line(grid, 1, 2, "ОТЧЕСТВО:")
        self._birth = self._line(grid, 2, 0, "ТУГИЛГАН САНА:")
        self._birth.setPlaceholderText("13.08.2009")
        self._citizenship = self._line(grid, 2, 2, "ГРАЖДАНСТВАСИ:")
        self._doc = self._line(grid, 3, 0, "ПАСПОРТ СЕРИЯ №:")
        self._doc.setPlaceholderText("FB2376204")
        self._gender = QComboBox()
        self._gender.addItem("— жинси —", "")
        self._gender.addItem("МУЖ (эркак)", "Мужской")
        self._gender.addItem("ЖЕН (аёл)", "Женский")
        grid.addWidget(QLabel("Жинси:"), 3, 2)
        grid.addWidget(self._gender, 3, 3)
        root.addLayout(grid)

        # -- what the office types itself -------------------------------
        own = QGridLayout()
        own.setHorizontalSpacing(14)
        self._series = self._line(own, 0, 0, "КАРТА СЕРИЯ:")
        self._series.setPlaceholderText("46 26")
        self._number = self._line(own, 0, 2, "КАРТА НОМЕР:")
        self._number.setPlaceholderText("0367598")
        self._visa = self._line(own, 1, 0, "ВИЗА № (бўлмаса бўш):")
        self._visa.setPlaceholderText("АШХ23652")
        own.addWidget(QLabel("Иш ўрни:"), 2, 0)
        jobs = QHBoxLayout()
        self._jobs: dict[str, QCheckBox] = {}
        for key, label, _rule in JOBS:
            box = QCheckBox(label)
            box.setToolTip("Белгиланса — бланкада шу сўзнинг тагига чизиқ "
                           "чизилади")
            jobs.addWidget(box)
            self._jobs[key] = box
        jobs.addStretch(1)
        own.addLayout(jobs, 2, 1, 1, 3)
        root.addLayout(own)

        dates = QHBoxLayout()
        dates.addWidget(QLabel("КАРТА АМАЛ КИЛИШ МУДАТИ — С:"))
        self._from = self._date_edit(QDate.currentDate())
        dates.addWidget(self._from)
        dates.addWidget(QLabel("ДО:"))
        self._to = self._date_edit(QDate.currentDate().addDays(90))
        dates.addWidget(self._to)
        dates.addWidget(QLabel("Берилган сана (кўк):"))
        self._issued = self._date_edit(QDate.currentDate())
        self._issued.setToolTip("Картанинг пастида, М.П. устида — кўк рангда")
        dates.addWidget(self._issued)
        dates.addStretch(1)
        root.addLayout(dates)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (ИШЧИ КАРТАСИ)")
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
            "Ҳар фирманинг ўз бланкаси ва ўз печати — юкланганлари сақланиб "
            "қолади. Печатни бир марта сичқонча билан жойига қўйинг, кейинги "
            "сафар ўша жойга, ўша ўлчамда тушади. Паспортдан фамилия, исм, "
            "отчество, туғилган сана, гражданство, жинс ва паспорт рақами "
            "ўқилади — қолганини ўзингиз киритасиз.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

        self._reload()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _line(grid: QGridLayout, row: int, col: int, label: str) -> QLineEdit:
        grid.addWidget(QLabel(label), row, col)
        edit = QLineEdit()
        grid.addWidget(edit, row, col + 1)
        return edit

    @staticmethod
    def _date_edit(when: QDate) -> QDateEdit:
        edit = QDateEdit()
        edit.setDisplayFormat("dd.MM.yyyy")
        edit.setDate(when)
        edit.setCalendarPopup(True)
        return edit

    def _reload(self) -> None:
        self._template.clear()
        for blank in self._c.templates():
            self._template.addItem(blank.stem, str(blank))
        if not self._template.count():
            self._template.addItem("— бланка юкланмаган —", None)

        self._stamp.clear()
        self._stamp.addItem("— печатсиз —", None)
        for stamp in self._c.stamps():
            self._stamp.addItem(stamp.name, str(stamp.path))

    def _chosen_stamp(self):
        path = self._stamp.currentData()
        if not path:
            return None
        for stamp in self._c.stamps():
            if str(stamp.path) == path:
                return stamp
        return None

    # ------------------------------------------------------- the firm
    def _add_template(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Фирманинг БЎШ ИШЧИ КАРТАСИ", str(_desktop()), _BLANK_FILTER)
        if not path:
            return
        name, ok = QInputDialog.getText(self, "Бланка номи",
                                        "Фирма номи:", text=Path(path).stem)
        if not ok or not name.strip():
            return
        try:
            dest = self._c.add_template(name, Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._template.setCurrentIndex(self._template.findData(str(dest)))
        self._status.setText(f"✅ Бланка қўшилди: {dest.stem}")

    def _remove_template(self) -> None:
        path = self._template.currentData()
        if not path:
            return
        if QMessageBox.question(self, "Ўчириш",
                                f"«{Path(path).stem}» бланкаси ўчирилсинми?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_template(Path(path))
        self._reload()

    def _add_stamp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Фирманинг ПЕЧАТИ", str(_desktop()), _STAMP_FILTER)
        if not path:
            return
        name, ok = QInputDialog.getText(self, "Печат номи",
                                        "Фирма номи:", text=Path(path).stem)
        if not ok or not name.strip():
            return
        try:
            stamp = self._c.add_stamp(name, Path(path))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._stamp.setCurrentIndex(self._stamp.findData(str(stamp.path)))
        self._status.setText(
            f"✅ Печат қўшилди: {stamp.name} — энди «🎯 Жойлаш» билан "
            "жойига қўйинг.")

    def _remove_stamp(self) -> None:
        stamp = self._chosen_stamp()
        if stamp is None:
            return
        if QMessageBox.question(self, "Ўчириш",
                                f"«{stamp.name}» печати ўчирилсинми?"
                                ) != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_stamp(stamp)
        self._reload()

    def _place_stamp(self) -> None:
        """Drag the stamp onto this firm's own blank and keep where it went."""
        stamp = self._chosen_stamp()
        template = self._template.currentData()
        if stamp is None or not template:
            self._warn("Аввал бланка ва печатни танланг.")
            return
        from src.pdf.mig_renderer import MigData, as_png, render
        from src.ui.widgets.stamp_placer import StampPlacer

        try:
            page = as_png(render(MigData(), Path(template)), zoom=1.4)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        dialog = StampPlacer(page, stamp.path.read_bytes(), stamp.box, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            self._c.place_stamp(stamp, dialog.box())
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._status.setText(f"✅ «{stamp.name}» печатининг жойи сақланди.")

    # ------------------------------------------------------- passport
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
                          (self._citizenship, "citizenship"),
                          (self._doc, "passport")):
            if fields.get(key):
                edit.setText(fields[key])
        gender = fields.get("gender", "")
        if gender:
            index = self._gender.findData(gender)
            if index >= 0:
                self._gender.setCurrentIndex(index)
        missing = [t for t, k in (("фамилия", "surname"),
                                  ("туғилган сана", "birth_date"),
                                  ("гражданство", "citizenship"),
                                  ("паспорт рақами", "passport"),
                                  ("жинси", "gender"))
                   if not fields.get(k)]
        self._status.setText(
            "✅ Паспорт ўқилди — текшириб RUN босинг."
            + (f"  ⚠️ Ўқилмади: {', '.join(missing)} — қўлда киритинг."
               if missing else ""))

    # ------------------------------------------------------- printing
    def _generate(self) -> None:
        template = self._template.currentData()
        chosen = tuple(key for key, box in self._jobs.items() if box.isChecked())
        try:
            result = self._c.generate(
                template=Path(template) if template else None,
                series=self._series.text(), number=self._number.text(),
                visa=self._visa.text(), jobs=chosen,
                valid_from=self._from.date().toPython(),
                valid_to=self._to.date().toPython(),
                issued_on=self._issued.date().toPython(),
                surname=self._surname.text(),
                surname_latin=self._surname_lat.text(),
                name=self._name.text(), patronymic=self._patronymic.text(),
                birth_date=self._c.parse_date(self._birth.text()),
                citizenship=self._citizenship.text(),
                passport=self._doc.text(),
                gender=self._gender.currentData() or "",
                stamp=self._chosen_stamp())
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        self._last = result.saved
        self._open.setEnabled(True)
        pix = QPixmap.fromImage(QImage.fromData(result.png, "PNG"))
        self._preview.setPixmap(pix.scaledToHeight(
            max(220, self._preview.height()),
            Qt.TransformationMode.SmoothTransformation))

        # the card is a PDF and the office files it per worker, so it is asked
        # where this one goes rather than always dropped in the same folder
        from src.ui.widgets.save_to import ask_save_dir

        chosen = ask_save_dir(self, [result.saved])
        self._status.setText(
            f"✅ {result.saved.name}" + (f" → {chosen}" if chosen else ""))

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
        """A new worker — the firm's blank, its stamp and the card stay."""
        self._passport.clear()
        for edit in (self._surname, self._surname_lat, self._name,
                     self._patronymic, self._birth, self._citizenship,
                     self._doc, self._series, self._number, self._visa):
            edit.clear()
        self._gender.setCurrentIndex(0)
        for box in self._jobs.values():
            box.setChecked(False)
        self._preview.clear()
        self._last = None
        self._open.setEnabled(False)
