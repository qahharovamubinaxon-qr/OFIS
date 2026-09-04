"""ТРУДАВОЙ + УВЕДОМЛЕНИЕ — the office's own blanks, the office's own map.

Nothing is built in. A firm is a name; the office uploads its EMPTY ТД and
УВ PDFs, and everything else happens in ONE window — «📐 ТД» / «📐 УВ» —
where a text is added, told what it means, dragged, sized, coloured, made
bold or thin and given its face. The worker's papers then come out on those
very blanks.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.logging import get_logger
from src.common.threading import run_async
from src.controllers.trud8_controller import Trud8Controller
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)

_PROFESSIONS = ("ПОДСОБНЫЙ РАБОЧИЙ", "РАЗНОРАБОЧИЙ", "УБОРЩИЦА", "КУРЬЕР",
                "МОНТАЖНИК", "ШТУКАТУР", "БЕТОНЩИК", "МАЛЯР")

_KINDS = (("ТД — трудовой договор", "td"), ("УВ — уведомление", "uv"))


class Trud8View(QWidget):
    def __init__(self, controller: Trud8Controller) -> None:
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

        title = QLabel("ТРУДАВОЙ + УВЕДОМЛЕНИЕ — ўз бланкангиз, ўз майдонларингиз")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        firm_row = QHBoxLayout()
        firm_row.addWidget(QLabel("Фирма:"))
        self._firm = QComboBox()
        self._firm.currentIndexChanged.connect(lambda _: self._show_state())
        firm_row.addWidget(self._firm, stretch=1)
        add_firm = QPushButton("➕ Фирма")
        add_firm.setToolTip("Фирма номини ёзасиз — бланкаларини кейин юклайсиз")
        add_firm.clicked.connect(self._add_firm)
        firm_row.addWidget(add_firm)
        drop = QPushButton("🗑 Фирма")
        drop.clicked.connect(self._remove_firm)
        firm_row.addWidget(drop)
        root.addLayout(firm_row)

        blank_row = QHBoxLayout()
        blank_row.addWidget(QLabel("Бўш бланка (PDF):"))
        set_td = QPushButton("📄 ТД юклаш")
        set_td.clicked.connect(lambda: self._set_blank("td"))
        blank_row.addWidget(set_td)
        set_uv = QPushButton("📄 УВ юклаш")
        set_uv.clicked.connect(lambda: self._set_blank("uv"))
        blank_row.addWidget(set_uv)
        blank_row.addStretch(1)
        root.addLayout(blank_row)

        field_row = QHBoxLayout()
        field_row.addWidget(QLabel("Матнлар:"))
        arrange_td = QPushButton("📐 ТД матнлари")
        arrange_td.setToolTip("Матн қўшиш, суриш, катта-кичик қилиш, ранг, "
                              "қалинлик ва шрифт — ҳаммаси шу ойнада")
        arrange_td.clicked.connect(lambda: self._arrange("td"))
        field_row.addWidget(arrange_td)
        arrange_uv = QPushButton("📐 УВ матнлари")
        arrange_uv.setToolTip("Матн қўшиш, суриш, катта-кичик қилиш, ранг, "
                              "қалинлик ва шрифт — ҳаммаси шу ойнада")
        arrange_uv.clicked.connect(lambda: self._arrange("uv"))
        field_row.addWidget(arrange_uv)
        field_row.addStretch(1)
        root.addLayout(field_row)

        self._state = QLabel("")
        self._state.setWordWrap(True)
        self._state.setStyleSheet("color:#8a94a3;")
        root.addWidget(self._state)

        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        self._passport.changed.connect(self._on_dropped)
        docs.addWidget(self._passport)
        self._front = DropZone("🩷", "Патент олди")
        self._front.changed.connect(self._on_dropped)
        docs.addWidget(self._front)
        self._back = DropZone("🩶", "Патент орқаси")
        self._back.changed.connect(self._on_dropped)
        docs.addWidget(self._back)
        root.addLayout(docs)

        # what was read, for the operator to check before printing
        from src.ui.widgets.passport_review import PassportReview
        self._review = PassportReview()
        root.addWidget(self._review)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(400)
        self._settle.timeout.connect(self._read_now)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        root.addLayout(grid)
        grid.addWidget(QLabel("Шартнома санаси:"), 0, 0)
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._date, 0, 1)
        grid.addWidget(QLabel("Должность (бўш — патентдан):"), 0, 2)
        self._profession = QComboBox()
        self._profession.setEditable(True)
        self._profession.addItem("")
        self._profession.addItems(_PROFESSIONS)
        grid.addWidget(self._profession, 0, 3)

        run_row = QHBoxLayout()
        self._run = QPushButton("🖨 Тайёрлаш")
        self._run.setObjectName("primaryButton")
        self._run.clicked.connect(self._generate)
        run_row.addWidget(self._run)
        open_out = QPushButton("📂 Папкани очиш")
        open_out.clicked.connect(self._open_folder)
        run_row.addWidget(open_out)
        run_row.addStretch(1)
        root.addLayout(run_row)

        self._progress = RunProgress(self)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)
        self._reload()

    # ------------------------------------------------------------- state
    def _reload(self) -> None:
        current = self._firm.currentData()
        self._firm.blockSignals(True)
        self._firm.clear()
        for firm in self._c.firms():
            self._firm.addItem(firm.name, str(firm))
        if self._firm.count() == 0:
            self._firm.addItem("— фирма йўқ, «➕ Фирма» —", None)
        elif current:
            index = self._firm.findData(current)
            if index >= 0:
                self._firm.setCurrentIndex(index)
        self._firm.blockSignals(False)
        self._show_state()

    def _show_state(self) -> None:
        firm = self._firm.currentData()
        if not firm:
            self._state.setText("Фирма қўшинг, сўнг унинг бўш ТД ва УВ "
                                "PDF ларини юкланг.")
            return
        firm = Path(firm)
        parts = []
        for label, kind in _KINDS:
            tag = label.split(" ")[0]
            if self._c.blank(firm, kind) is None:
                parts.append(f"{tag}: бланка йўқ")
                continue
            count = len(self._c.fields(firm, kind))
            parts.append(f"{tag}: {self._c.pages(firm, kind)} варақ, "
                         f"{count} та матн")
        self._state.setText(" · ".join(parts))

    def _firm_now(self) -> Path | None:
        firm = self._firm.currentData()
        if not firm:
            self._warn("Аввал фирмани танланг ёки «➕ Фирма» билан қўшинг.")
            return None
        return Path(firm)

    # ------------------------------------------------------------- firms
    def _add_firm(self) -> None:
        name, ok = QInputDialog.getText(self, "Янги фирма", "Фирма номи:")
        if not ok or not name.strip():
            return
        try:
            made = self._c.add_firm(name.strip())
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        index = self._firm.findData(str(made))
        if index >= 0:
            self._firm.setCurrentIndex(index)
        self._status.setText(f"✅ «{made.name}» қўшилди — энди унинг бўш ТД ва "
                             "УВ PDF ларини юкланг.")

    def _remove_firm(self) -> None:
        firm = self._firm_now()
        if firm is None:
            return
        if QMessageBox.question(
                self, "Ўчириш",
                f"«{firm.name}» фирмаси (бланка ва матнлари билан) "
                "ўчирилсинми?") != QMessageBox.StandardButton.Yes:
            return
        self._c.remove_firm(firm)
        self._reload()

    # ------------------------------------------------------------ blanks
    def _set_blank(self, kind: str) -> None:
        firm = self._firm_now()
        if firm is None:
            return
        tag = "ТД" if kind == "td" else "УВ"
        source, _ = QFileDialog.getOpenFileName(
            self, f"{tag} — бўш бланка PDF", "", "Бланка (*.pdf)")
        if not source:
            return
        try:
            self._c.set_blank(firm, kind, Path(source))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._show_state()
        self._status.setText(
            f"✅ {tag} бланкаси юкланди ({self._c.pages(firm, kind)} варақ) — "
            "«➕ Матн» билан майдонларни қўйинг.")

    # ------------------------------------------------------------ fields
    def _arrange(self, kind: str) -> None:
        """One window: add, place, colour, weight, face — then save."""
        firm = self._firm_now()
        if firm is None:
            return
        import fitz

        from src.ui.widgets.field_editor import FieldEditor

        blank = self._c.blank(firm, kind)
        if blank is None:
            self._warn("Бу фирмада бундай бланка йўқ — аввал PDF ини юкланг.")
            return
        try:
            pages = []
            with fitz.open(str(blank)) as doc:
                for page in doc:
                    pages.append(page.get_pixmap(dpi=100).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        tag = "ТД" if kind == "td" else "УВ"
        dialog = FieldEditor(pages, self._c.fields(firm, kind),
                             title=f"{firm.name} — {tag}", parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            kept = dialog.fields()
            self._c.save_fields(firm, kind, kept)
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._show_state()
        self._status.setText(f"✅ {tag}: {len(kept)} та матн сақланди.")

    # ---------------------------------------------------------- printing
    # ------------------------------------------------------------ reading
    def _on_dropped(self) -> None:
        """The passport landed — read it at once, like every other section.

        The ТД/УВ also print the patent's own number and dates, so the patent
        front is asked for at print time; but the read must not wait for it in
        silence — that dead screen was «ишламаяпти»."""
        log.info("ТРУД(trud8) файл ташланди: passport=%s, front=%s, ai=%s",
                 self._passport.path is not None, self._front.path is not None,
                 self._c.ai_available())
        if self._passport.path is None or not self._c.ai_available():
            log.info("ТРУД(trud8): ўқиш бошланмади (паспорт йўқ ёки AI йўқ)")
            return
        self._settle.start()

    def _read_now(self) -> None:
        if self._passport.path is None or not self._c.ai_available():
            return
        log.info("ТРУД(trud8): ЎҚИШ БОШЛАНДИ")
        try:
            passport = self._c.read_image(self._passport.path)
            front = (self._c.read_image(self._front.path)
                     if self._front.path is not None else None)
            back = (self._c.read_image(self._back.path)
                    if self._back.path is not None else None)
            log.info("ТРУД(trud8): расмлар ўқилди — passport=%d bytes, "
                     "front=%s, back=%s", len(passport),
                     front is not None, back is not None)
            self._review.start_reading()
            self._status.setText("⏳ AI ҳужжатларни ўқияпти…")
            self._progress.start("Ҳужжатлар ўқиляпти…")
            run_async(self._c.read_documents, passport, front, back,
                      on_success=self._filled, on_error=self._read_failed)
            log.info("ТРУД(trud8): run_async ишга туширилди — AIни кутмоқда")
        except Exception:
            log.exception("ТРУД(trud8): _read_now да КУТИЛМАГАН ХАТО")
            raise

    def _filled(self, pair) -> None:
        self._progress.finish()
        passport, patent = pair
        self._review.fill(passport, patent)
        self._status.setText("✅ Ўқилди — текширинг, хатоси бўлса тўғриланг, "
                             "кейин Тайёрлаш.")

    def _read_failed(self, error: Exception) -> None:
        self._progress.finish()
        self._review.reveal()          # so it can be typed by hand
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ Ўқилмади: {message}. Қўлда ёзинг.")

    # ------------------------------------------------------------ printing
    def _generate(self) -> None:
        firm = self._firm_now()
        if firm is None:
            return
        from src.ui.widgets.passport_review import ready_or_start
        if not ready_or_start(
                self._review, has_images=self._passport.path is not None,
                ai_available=self._c.ai_available(), start_read=self._read_now,
                warn=self._warn, no_images_msg="Паспорт расмини ташланг."):
            return
        if not self._review.has_surname():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return
        # the ТД/УВ print the patent's own number and dates, so the patent
        # front is required to print (the passport alone already read above —
        # this gates PRINTING only, never the read).
        if self._front.path is None:
            self._warn("Патент олди расмини ҳам ташланг — ТД/УВ унинг рақами "
                       "ва саналарини босади.")
            return
        when = self._date.date().toPython()
        profession = self._profession.currentText().strip()

        self._run.setEnabled(False)
        self._progress.start("ТД ва УВ тайёрланаяпти…")
        run_async(
            self._c.generate,
            firm=firm, passport=self._review.edited(),
            patent=self._review.edited_patent(),
            profession=profession, deal_date=when,
            on_success=self._done, on_error=self._failed)

    def _done(self, result) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        self._passport.clear()
        self._front.clear()
        self._back.clear()
        self._review.reset()
        names = ", ".join(p.name for p in result.saved)
        self._status.setText(f"✅ Тайёр: {names}")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "trud"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
