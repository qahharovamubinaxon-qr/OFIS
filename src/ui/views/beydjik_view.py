"""БЕЙДЖИК screen — the office's own worker ID badge.

Pick the region (77 Москва / 50 Московская область), drop the worker's photo
and passport, choose the date and type the badge fields → RUN. The должность
line only exists on the область layout, so it is shown only for region 50.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.common.threading import run_async
from src.controllers.beydjik_controller import BeydjikController
from src.services.beydjik_service import REGIONS, BeydjikResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class BeydjikView(QWidget):
    def __init__(self, controller: BeydjikController) -> None:
        super().__init__()
        self._c = controller
        self._result: BeydjikResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        title = QLabel("БЕЙДЖИК — ишчининг бейджиги")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel("Шаблон:"))
        self._region = QComboBox()
        for code, label in self._c.regions():
            self._region.addItem(label, code)
        self._region.currentIndexChanged.connect(self._region_changed)
        self._region.setMinimumWidth(230)
        top.addWidget(self._region)
        top.addSpacing(16)
        top.addWidget(QLabel("Кун:"))
        from PySide6.QtWidgets import QDateEdit

        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setDate(QDate.currentDate())
        self._date.setCalendarPopup(True)
        top.addWidget(self._date)
        top.addStretch(1)
        top.addWidget(QLabel("Кейинги ПР:"))
        self._pr = QLineEdit()
        self._pr.setPlaceholderText("4875056")
        self._pr.setFixedWidth(110)
        self._pr.setToolTip("Ҳар бейджикда автомат биттага ошади.")
        top.addWidget(self._pr)
        root.addLayout(top)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)

        form.addWidget(QLabel("Регион:"), 0, 0)
        self._region_code = QLineEdit()
        self._region_code.setPlaceholderText("77")
        self._region_code.setMaxLength(4)
        self._region_code.setFixedWidth(70)
        form.addWidget(self._region_code, 0, 1)

        form.addWidget(QLabel("Шахсий номер:"), 0, 2)
        self._personal = QLineEdit()
        self._personal.setPlaceholderText("2600263521")
        self._personal.setMaxLength(20)
        form.addWidget(self._personal, 0, 3)

        form.addWidget(QLabel("ИНН:"), 1, 0)
        self._inn = QLineEdit()
        self._inn.setPlaceholderText("772998449826")
        self._inn.setMaxLength(20)
        form.addWidget(self._inn, 1, 1)

        form.addWidget(QLabel("Фирма (кем выдано):"), 1, 2)
        firm_row = QHBoxLayout()
        firm_row.setSpacing(4)
        self._firm = QLineEdit()
        self._firm.setText(self._c.firm())
        firm_row.addWidget(self._firm, stretch=1)
        # the office runs several companies — the ones already used are offered
        # back here instead of being retyped
        self._firm_pick = QToolButton()
        self._firm_pick.setText("▾")
        self._firm_pick.setToolTip("Аввал ёзилган фирмалар")
        self._firm_pick.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._firm_menu = QMenu(self._firm_pick)
        self._firm_menu.aboutToShow.connect(self._fill_firm_menu)
        self._firm_pick.setMenu(self._firm_menu)
        firm_row.addWidget(self._firm_pick)
        form.addLayout(firm_row, 1, 3)

        form.addWidget(QLabel("Территория действия патента:"), 2, 0)
        self._territory = QLineEdit()
        self._territory.setPlaceholderText("г. Москва")
        form.addWidget(self._territory, 2, 1, 1, 3)

        self._dolzh_label = QLabel("Должность:")
        form.addWidget(self._dolzh_label, 3, 0)
        self._dolzhnost = QLineEdit()
        self._dolzhnost.setPlaceholderText("Водитель")
        form.addWidget(self._dolzhnost, 3, 1, 1, 3)
        form.setColumnStretch(3, 1)
        root.addLayout(form)

        zones = QHBoxLayout()
        self._photo = DropZone("📷", "Ишчининг расми")
        self._passport = DropZone("🛂", "Ишчининг паспорти")
        zones.addWidget(self._photo)
        zones.addWidget(self._passport)
        root.addLayout(zones, stretch=1)

        actions = QHBoxLayout()
        self._run = QPushButton("▶  RUN (БЕЙДЖИК)")
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
            "Шаблонни танланг, ишчининг расми ва паспортини юкланг. Ф.И.О., "
            "туғилган санаси, фуқаролиги ва паспорт рақами паспортдан олинади. "
            "«Кейинги ПР» га бошланғич рақамни ёзинг — ҳар бейджикда битта "
            "ошиб боради.")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._status)

        self._region_changed()

    # ------------------------------------------------------------------
    def _current_region(self) -> str:
        return str(self._region.currentData() or "77")

    def _region_changed(self) -> None:
        code = self._current_region()
        wants = bool(REGIONS.get(code, {}).get("dolzhnost"))
        self._dolzh_label.setVisible(wants)
        self._dolzhnost.setVisible(wants)
        if not self._region_code.text().strip():
            self._region_code.setText(code)
        # the region's own wording is a suggestion the operator may overwrite
        self._territory.setText(self._c.territory(code))
        self._show_pr()

    def _show_pr(self) -> None:
        self._pr.setText(self._c.next_pr())

    def _fill_firm_menu(self) -> None:
        """Rebuild the list each time — a badge just made may have added to it."""
        self._firm_menu.clear()
        firms = self._c.firms()
        for name in firms:
            self._firm_menu.addAction(name).triggered.connect(
                lambda _=False, n=name: self._firm.setText(n))
        if firms:
            self._firm_menu.addSeparator()
        clear = self._firm_menu.addAction("🗑  Рўйхатни тозалаш")
        clear.setEnabled(bool(firms))
        clear.triggered.connect(self._forget_firms)

    def _forget_firms(self) -> None:
        if QMessageBox.question(
                self, "Тозалаш", "Сақланган фирмалар рўйхати ўчирилсинми?"
        ) == QMessageBox.StandardButton.Yes:
            self._c.forget_firms()

    def _issue_date(self) -> date:
        q = self._date.date()
        return date(q.year(), q.month(), q.day())

    def _run_ai(self) -> None:
        if self._passport.path is None:
            self._warn("Ишчининг паспорти расмини юкланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalarга Gemini калитини киритинг.")
            return
        if not self._personal.text().strip():
            self._warn("Шахсий номерни киритинг.")
            return
        # the operator may retype the serial to start a new run of blanks
        try:
            self._c.set_next_pr(self._pr.text())
        except OfisError as exc:
            self._warn(exc.message)
            return

        data = Path(self._passport.path).read_bytes()
        photo = Path(self._photo.path) if self._photo.path else None
        self._run.setEnabled(False)
        self._status.setText("⏳ Паспорт ўқилаяпти ва бейджик тайёрланяпти…")
        self._progress.start("Бейджик тайёрланяпти…")
        run_async(
            self._c.generate_from_image, data,
            region=self._current_region(),
            personal_number=self._personal.text().strip(),
            inn=self._inn.text().strip(),
            issue_date=self._issue_date(),
            firm=self._firm.text().strip() or None,
            dolzhnost=self._dolzhnost.text().strip(),
            territory=self._territory.text().strip(),
            photo_path=photo,
            on_success=self._done, on_error=self._failed)

    def _done(self, result: BeydjikResult) -> None:
        self._run.setEnabled(True)
        self._open.setEnabled(True)
        self._progress.finish()
        self._result = result
        self._photo.clear()
        self._passport.clear()
        self._status.setText(
            f"✅ {result.surname} — ПР {result.pr_number} "
            f"({result.region})\n{result.pdf_path}")
        self._show_pr()

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

        QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self._result.pdf_path.parent)))

    def _warn(self, message: str) -> None:
        self._status.setText("⚠️ " + message)
        QMessageBox.information(self, "Diqqat", message)

    # -- «Обновить» support -------------------------------------------
    def reset(self) -> None:
        self._photo.clear()
        self._passport.clear()
        self._personal.clear()
        self._inn.clear()
        self._dolzhnost.clear()
        self._result = None
        self._open.setEnabled(False)
        self._region_changed()
