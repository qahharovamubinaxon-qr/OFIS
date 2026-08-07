"""АМИНА — a worker's account in the office's own app, opened from here.

The office drops the passport, types the phone, the address and the card's
number, and drops however many document photographs it has. What comes back
is the login and the password to hand the worker.

Two things this screen insists on. Every value the reader offers lands in a
box that can be typed over — the office corrects, then runs. And the login and
the password are shown *while* the phone is being typed, not after the account
exists: they are made out of the phone, so a wrong digit is a wrong password,
and it is far better seen before Firebase has it than after.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.threading import run_async
from src.controllers.amina_controller import AminaController
from src.services.amina_service import AminaData, AminaResult
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress


class AminaView(QWidget):
    def __init__(self, controller: AminaController) -> None:
        super().__init__()
        self._c = controller

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(12)

        title = QLabel("АМИНА — ишчига аккаунт очиш")
        title.setObjectName("viewTitle")
        root.addWidget(title)
        note = QLabel(
            "Паспортни ташланг → «Ўқиш» → телефон, адрес ва карта рақамини "
            "ёзинг → ҳужжат расмларини ўз майдонига ташланг → «Аккаунт "
            "очиш». Ҳар расм кесилиб, оқ А4 марказига қўйилиб, imgbb'га "
            "чиқади ва ҳаволаси Экселдаги ўз қаторига тушади. Нечта расм "
            "ташласангиз — ўшалар боради, қолгани бўш қолади.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#8a94a3;")
        root.addWidget(note)

        top = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        top.addWidget(self._passport)
        read = QPushButton("📖 Ўқиш")
        read.setToolTip("Паспортдан ФИО, туғилган сана, туғилган жой ва "
                        "гражданство олинади")
        read.clicked.connect(self._read)
        top.addWidget(read)
        top.addStretch(1)
        root.addLayout(top)

        # ------------------------------------------------------ the worker
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        root.addLayout(form)

        self._full_name = self._box(form, 0, 0, "ФИО:",
                                    "Шарипов Эхромиддин Талбишоевич", span=3)
        form.addWidget(QLabel("Жинси:"), 1, 0)
        self._gender = QComboBox()
        self._gender.addItems(["Мужской", "Женский"])
        form.addWidget(self._gender, 1, 1)

        form.addWidget(QLabel("Туғилган сана:"), 1, 2)
        self._dob = QDateEdit(QDate(1998, 1, 20))
        self._dob.setCalendarPopup(True)
        self._dob.setDisplayFormat("dd-MM-yyyy")
        form.addWidget(self._dob, 1, 3)

        self._birth_place = self._box(form, 2, 0, "Туғилган жой:",
                                      "Таджикистан")
        self._citizenship = self._box(form, 2, 2, "Гражданство:",
                                      "Республика Таджикистан")

        kept = self._c.typed()
        self._phone = self._box(form, 3, 0, "Телефон:", "+7 996 681-84-92")
        self._phone.setToolTip("Парол шундан ясалади: +7 ўрнига 8 қўйилади")
        self._phone.textChanged.connect(self._show_account)
        self._extra_phone = self._box(form, 3, 2, "Қўшимча телефон:",
                                      "Бўш қолса — юқоридагиси")
        self._extra_phone.setText(kept.get("extra_phone", ""))

        self._city = self._box(form, 4, 0, "Шаҳар:", "Москва")
        self._city.setText(kept.get("city", "") or "Москва")
        self._street = self._box(form, 4, 2, "Кўча:", "улица Беловежская")
        self._house = self._box(form, 5, 0, "Уй:", "71")
        self._apartment = self._box(form, 5, 2, "Хонадон:", "94")

        self._kig_number = self._box(form, 6, 0, "КИГ рақами:", "АВ0461171")
        self._kig_number.setToolTip("Картанинг серия-номери — ўзингиз ёзасиз")
        form.addWidget(QLabel("КИГ тугаш санаси:"), 6, 2)
        self._kig_expire = QDateEdit(QDate(2031, 6, 5))
        self._kig_expire.setCalendarPopup(True)
        self._kig_expire.setDisplayFormat("yyyy-MM-dd")
        self._kig_expire.setToolTip("Картанинг амал қилиш муддати")
        form.addWidget(self._kig_expire, 6, 3)

        # --------------------------------------------------- the documents
        docs = QGroupBox("Ҳужжат расмлари — ташлаганингиз боради")
        grid = QGridLayout(docs)
        grid.setHorizontalSpacing(10)
        # Three across, wrapping — five side by side runs off the edge of a
        # normal window and gives the whole screen a horizontal scrollbar.
        self._zones: dict[str, DropZone] = {}
        for index, key in enumerate(self._c.docs()):
            many = self._c.doc_limit(key) > 1
            name = self._c.doc_names()[key]
            zone = DropZone("📄", f"{name} · {key}", multiple=many)
            zone.setToolTip(
                "Айди-паспортнинг олди ва орқасини бирга ташланг — иккови "
                "битта оқ А4 қоғозга тушади" if many else
                f"«{key}» қаторига шу расмнинг ҳаволаси ёзилади")
            grid.addWidget(zone, index // 3, index % 3)
            self._zones[key] = zone
        root.addWidget(docs)

        # ------------------------------------------------------ the account
        account = QGroupBox("Ишчига бериладигани")
        acc = QGridLayout(account)
        acc.addWidget(QLabel("Логин:"), 0, 0)
        self._login = QLineEdit()
        self._login.setReadOnly(True)
        self._login.setPlaceholderText("фамилия + телефоннинг охирги 4 рақами")
        acc.addWidget(self._login, 0, 1)
        acc.addWidget(QLabel("Парол:"), 0, 2)
        self._password = QLineEdit()
        self._password.setReadOnly(True)
        self._password.setPlaceholderText("телефон, +7 ўрнига 8")
        acc.addWidget(self._password, 0, 3)
        root.addWidget(account)

        run_row = QHBoxLayout()
        self._run = QPushButton("🚀 Аккаунт очиш")
        self._run.setObjectName("primaryButton")
        self._run.setToolTip("Расмлар imgbb'га → Эксел тўлади → "
                             "npm install ва npm run import ишлайди")
        self._run.clicked.connect(self._create)
        run_row.addWidget(self._run)
        show = QPushButton("📋 Экселни кўриш")
        show.setToolTip("Ҳозир Экселда нима ёзилганини кўрсатади")
        show.clicked.connect(self._show_excel)
        run_row.addWidget(show)
        run_row.addStretch(1)
        root.addLayout(run_row)

        self._progress = RunProgress(self)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self._status)

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setFixedHeight(120)
        self._output.setPlaceholderText(
            "Терминал жавоби шу ерда кўринади (npm install, npm run import)")
        root.addWidget(self._output)
        root.addStretch(1)

        self._show_account()

    @staticmethod
    def _box(form: QGridLayout, row: int, column: int, label: str,
             hint: str, span: int = 1) -> QLineEdit:
        form.addWidget(QLabel(label), row, column)
        edit = QLineEdit()
        edit.setPlaceholderText(hint)
        form.addWidget(edit, row, column + 1, 1, span)
        return edit

    # --------------------------------------------------------------- state
    def _surname(self) -> str:
        """The first word of the full name — a login is built off it."""
        said = self._full_name.text().strip().split()
        return said[0] if said else ""

    def _show_account(self) -> None:
        """The login and password, live, while the phone is still being typed."""
        phone = self._phone.text()
        self._login.setText(self._c.email_of(self._surname(), phone))
        self._password.setText(self._c.password_of(phone))

    def _data(self) -> AminaData:
        """What is in the boxes — never what was read, always what is shown."""
        return AminaData(
            full_name=self._full_name.text().strip(),
            gender=self._gender.currentText(),
            dob=self._dob.date().toString("dd-MM-yyyy"),
            birth_place=self._birth_place.text().strip(),
            citizenship=self._citizenship.text().strip(),
            phone=self._phone.text().strip(),
            extra_phone=self._extra_phone.text().strip(),
            street=self._street.text().strip(),
            house=self._house.text().strip(),
            apartment=self._apartment.text().strip(),
            city=self._city.text().strip() or "Москва",
            kig_number=self._kig_number.text().strip(),
            kig_expire=self._kig_expire.date().toString("yyyy-MM-dd"))

    def _images(self) -> dict[str, list[bytes]]:
        """Only the fields that actually got a picture."""
        out: dict[str, list[bytes]] = {}
        for key, zone in self._zones.items():
            chosen = zone.paths or ([zone.path] if zone.path else [])
            if chosen:
                out[key] = [self._c.read_image(Path(p)) for p in chosen]
        return out

    # ------------------------------------------------------------- reading
    def _read(self) -> None:
        if self._passport.path is None:
            self._warn("Паспорт расмини ташланг.")
            return
        if not self._c.ai_available():
            self._warn("AI калити йўқ — Sozlamalar бўлимига калит киритинг.")
            return
        image = Path(self._passport.path).read_bytes()
        self._run.setEnabled(False)
        self._progress.start("Паспорт ўқиляпти…")
        run_async(lambda: self._c.read_passport(image),
                  on_success=self._filled, on_error=self._failed)

    def _filled(self, data: AminaData) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._full_name.setText(data.full_name)
        self._gender.setCurrentText(data.gender or "Мужской")
        self._birth_place.setText(data.birth_place)
        self._citizenship.setText(data.citizenship)
        if data.dob:
            self._dob.setDate(QDate.fromString(data.dob, "dd-MM-yyyy"))
        self._show_account()
        self._status.setText(
            "✅ Ўқилди — текширинг, телефон ва адресни ёзинг.")

    # -------------------------------------------------------------- making
    def _create(self) -> None:
        try:
            self._c.check()
        except Exception as exc:                          # noqa: BLE001
            self._warn(str(exc))
            return
        if self._c.excel_is_open():
            self._warn("Эксел ҳозир очиқ турибди — ёпинг, кейин уриниб "
                       "кўринг. Акс ҳолда ёзилгани сақланмайди.")
            return

        data = self._data()
        images = self._images()
        if not data.full_name:
            self._warn("ФИО керак — паспортни ўқитинг ёки қўлда ёзинг.")
            return
        if not data.phone.strip():
            self._warn("Телефон рақами керак — парол ундан ясалади.")
            return
        if not images:
            asked = QMessageBox.question(
                self, "Расмсиз",
                "Битта ҳам ҳужжат расми ташланмади. Аккаунт ҳужжатларсиз "
                "очилсинми?")
            if asked != QMessageBox.StandardButton.Yes:
                return

        self._c.remember_typed(city=self._city.text(),
                               extra_phone=self._extra_phone.text())
        self._run.setEnabled(False)
        self._output.clear()
        self._progress.start(
            f"{len(images)} та расм чиқиб, Эксел тўлиб, импорт ишлаяпти…")
        run_async(lambda: self._c.create(data, images),
                  on_success=self._made, on_error=self._failed)

    def _made(self, result: AminaResult) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._login.setText(result.login)
        self._password.setText(result.password)
        self._output.setPlainText(result.output)
        went = ", ".join(self._c.doc_names()[k] for k in self._c.docs()
                         if k in result.urls) or "ҳужжатсиз"
        self._status.setText(
            f"✅ Аккаунт очилди — {went}.\n{result.slip()}")

    # --------------------------------------------------------------- extras
    def _show_excel(self) -> None:
        try:
            rows = self._c.excel()
        except Exception as exc:                          # noqa: BLE001
            self._warn(str(exc))
            return
        lines = "\n".join(f"{k:18} {v}" for k, v in rows.items())
        box = QMessageBox(self)
        box.setWindowTitle("Экселда ҳозир нима бор")
        box.setText(f"{self._c.folder()}")
        box.setDetailedText(lines)
        box.exec()

    def _failed(self, exc: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._status.setText(f"❌ {exc}")
        self._warn(str(exc))

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self, "АМИНА", text)


__all__ = ["AminaView"]
