"""АЛЬЯНСКОТ 2400 — the firm's удостоверение and two справки, one press.

The office uploads three empty blanks (the удостоверение is two pages), lays
its own fields on each with «📐 Жойлаш» (the ТРУД-8 arranger — text, photo and
signature all dragged into place), drops the worker's passport (read on the
spot into the shared check panel) and photo, the worker signs with the mouse,
and «🖨 Тайёрлаш» prints all three as separate PDFs named after the worker.
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
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.logging import get_logger
from src.common.threading import run_async
from src.controllers.alliance_controller import AllianceController
from src.services.alliance_service import SLOT_LABELS, SLOTS
from src.ui.widgets.drop_zone import DropZone
from src.ui.widgets.run_progress import RunProgress

log = get_logger(__name__)

_DOLZHNOSTI = ("ПОДСОБНЫЙ РАБОЧИЙ", "РАЗНОРАБОЧИЙ", "МОНТАЖНИК", "ШТУКАТУР",
               "БЕТОНЩИК", "МАЛЯР", "СВАРЩИК", "ЭЛЕКТРИК")

_SLOT_TITLES = {"udo": "Удостоверение (2 бет):", "spr1": "Справка 1:",
                "spr2": "Справка 2:"}


class AllianceView(QWidget):
    def __init__(self, controller: AllianceController) -> None:
        super().__init__()
        self._c = controller
        self._signature: bytes | None = None
        self._slot_state: dict[str, QLabel] = {}

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

        title = QLabel("АЛЬЯНСКОТ 2400 — удостоверение + 2 справка")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        hint = QLabel("Учта бўш бланкани юкланг, ҳар бирида «📐 Жойлаш» билан "
                      "майдон/расм/имзо жойини созланг. Кейин паспорт ва расм "
                      "ташлаб «🖨 Тайёрлаш» — учаласи алоҳида PDF бўлади.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8a94a3;")
        root.addWidget(hint)

        for slot in SLOTS:
            self._add_blank_row(root, slot)

        docs = QHBoxLayout()
        self._passport = DropZone("🛂", "Паспорт")
        self._passport.changed.connect(self._on_dropped)
        docs.addWidget(self._passport)
        self._photo = DropZone("📷", "Ишчининг ўз расми")
        docs.addWidget(self._photo)
        root.addLayout(docs)

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
        grid.addWidget(QLabel("Удостоверение №:"), 0, 0)
        self._ud_number = QLineEdit()
        self._ud_number.setPlaceholderText("масалан 2400-0145")
        grid.addWidget(self._ud_number, 0, 1)
        grid.addWidget(QLabel("Должность:"), 0, 2)
        self._dolzhnost = QComboBox()
        self._dolzhnost.setEditable(True)
        self._dolzhnost.addItem("")
        self._dolzhnost.addItems(_DOLZHNOSTI)
        grid.addWidget(self._dolzhnost, 0, 3)
        grid.addWidget(QLabel("Бошланиш санаси:"), 1, 0)
        self._start = QDateEdit(QDate.currentDate())
        self._start.setCalendarPopup(True)
        self._start.setDisplayFormat("dd.MM.yyyy")
        self._start.dateChanged.connect(self._show_until)
        grid.addWidget(self._start, 1, 1)
        grid.addWidget(QLabel("Тугаш (ўзи +3 йил):"), 1, 2)
        self._until_label = QLabel("")
        grid.addWidget(self._until_label, 1, 3)

        sign_row = QHBoxLayout()
        sign = QPushButton("✍ Имзо қўйиш (ишчи)")
        sign.clicked.connect(self._sign)
        sign_row.addWidget(sign)
        self._sign_state = QLabel("Имзо: ҳали қўйилмаган ⚠️")
        sign_row.addWidget(self._sign_state)
        sign_row.addStretch(1)
        root.addLayout(sign_row)

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
        self._show_until()

    # ------------------------------------------------------------- blanks
    def _add_blank_row(self, root: QVBoxLayout, slot: str) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel(_SLOT_TITLES[slot]))
        up = QPushButton("📄 Юклаш")
        up.clicked.connect(lambda _=False, s=slot: self._set_blank(s))
        row.addWidget(up)
        arrange = QPushButton("📐 Жойлаш")
        arrange.setToolTip("Матн, расм ва имзо жойини суриш ва размерлаш")
        arrange.clicked.connect(lambda _=False, s=slot: self._arrange(s))
        row.addWidget(arrange)
        state = QLabel("")
        state.setStyleSheet("color:#8a94a3;")
        row.addWidget(state, stretch=1)
        self._slot_state[slot] = state
        root.addLayout(row)

    def _reload(self) -> None:
        for slot in SLOTS:
            if self._c.blank(slot) is None:
                self._slot_state[slot].setText("бланка юкланмаган")
                continue
            fields = len((self._c.layout(slot) or {}).get("fields") or [])
            self._slot_state[slot].setText(
                f"{self._c.pages(slot)} бет · {fields} та майдон")

    def _set_blank(self, slot: str) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, f"{SLOT_LABELS[slot]} — бўш бланка PDF", "", "Бланка (*.pdf)")
        if not source:
            return
        try:
            self._c.set_blank(slot, Path(source))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return
        self._reload()
        self._status.setText(f"✅ {SLOT_LABELS[slot]} бланкаси юкланди — "
                             "«📐 Жойлаш» билан майдонларни қўйинг.")

    def _arrange(self, slot: str) -> None:
        blank = self._c.blank(slot)
        if blank is None:
            self._warn(f"Аввал «{SLOT_LABELS[slot]}» бланкасини юкланг.")
            return
        import fitz

        from src.pdf.alliance_fields import CATALOGUE, IMG_LABELS, SAMPLES, Field
        from src.ui.widgets.field_editor import FieldEditor

        try:
            pages = []
            with fitz.open(str(blank)) as doc:
                for page in doc:
                    pages.append(page.get_pixmap(dpi=110).tobytes("png"))
        except Exception as error:                # noqa: BLE001
            self._failed(error)
            return

        saved = (self._c.layout(slot) or {}).get("fields") or []
        fields = [Field.from_dict(d) for d in saved if isinstance(d, dict)]
        dialog = FieldEditor(
            pages, fields, title=f"АЛЬЯНСКОТ — {SLOT_LABELS[slot]}", parent=self,
            catalogue={**CATALOGUE, **IMG_LABELS}, samples=SAMPLES,
            images=self._sample_images())
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        kept = dialog.fields()
        self._c.save_layout(slot, {"fields": [f.as_dict() for f in kept]})
        self._reload()
        self._status.setText(
            f"✅ {SLOT_LABELS[slot]}: {len(kept)} та майдон жойлаштирилди.")

    @staticmethod
    def _sample_images() -> dict[str, bytes]:
        """Grey stand-ins shown in the arranger where the photo and signature
        will land — one 3×4, one wide — so the office can size their boxes."""
        import io

        from PIL import Image

        def box(width: int, height: int, colour) -> bytes:
            out = io.BytesIO()
            Image.new("RGB", (width, height), colour).save(out, "PNG")
            return out.getvalue()

        return {"img_photo": box(300, 411, (208, 214, 223)),
                "img_sign": box(360, 130, (224, 228, 234))}

    # --------------------------------------------------------- signature
    def _sign(self) -> None:
        from src.ui.widgets.signature_pad import SignaturePad

        pad = SignaturePad(self)
        if pad.exec() != pad.DialogCode.Accepted:
            return
        self._signature = pad.signature_png()
        self._sign_state.setText(
            "Имзо: қўйилди ✅" if self._signature
            else "Имзо: ҳали қўйилмаган ⚠️")

    # ------------------------------------------------------------- dates
    def _show_until(self) -> None:
        until = self._c.until(self._start.date().toPython())
        self._until_label.setText(f"{until:%d.%m.%Y}" if until else "")

    # ------------------------------------------------------------ reading
    def _on_dropped(self) -> None:
        if self._passport.path is None or not self._c.ai_available():
            return
        self._settle.start()

    def _read_now(self) -> None:
        if self._passport.path is None or not self._c.ai_available():
            return
        passport = self._c.read_image(self._passport.path)
        self._review.start_reading()
        self._status.setText("⏳ Паспорт ўқиляпти…")
        self._progress.start("Паспорт ўқиляпти…")
        run_async(self._c.read_documents, passport,
                  on_success=self._filled, on_error=self._read_failed)

    def _filled(self, passport) -> None:
        self._progress.finish()
        self._review.fill(passport)
        self._status.setText("✅ Ўқилди — текширинг, хатоси бўлса тўғриланг, "
                             "кейин Тайёрлаш.")

    def _read_failed(self, error: Exception) -> None:
        self._progress.finish()
        self._review.reveal()
        message = getattr(error, "message", None) or str(error)
        log.warning("АЛЬЯНСКОТ ЎҚИШ ХАТО: %r", error)
        self._status.setText(f"❌ Ўқилмади: {message}. Қўлда ёзинг.")
        QMessageBox.warning(
            self, "AI ҳужжатни ўқий олмади",
            f"Сабаби:\n{message}\n\nМайдонларни қўлда ҳам тўлдиришингиз мумкин.")

    # ---------------------------------------------------------- printing
    def _generate(self) -> None:
        from src.domain.enums import Gender
        from src.ui.widgets.passport_review import ready_or_start

        if not ready_or_start(
                self._review, has_images=self._passport.path is not None,
                ai_available=self._c.ai_available(), start_read=self._read_now,
                warn=self._warn, no_images_msg="Паспорт расмини ташланг."):
            return
        if not self._review.has_surname():
            self._warn("Фамилия бўш — ўқилганини текширинг.")
            return
        missing = [SLOT_LABELS[s] for s in SLOTS if self._c.blank(s) is None]
        if missing:
            self._warn(f"Бланка юкланмаган: {', '.join(missing)} — "
                       "учаласини ҳам юкланг.")
            return
        if self._photo.path is None:
            self._warn("Ишчининг ўз расмини ташланг.")
            return
        if self._signature is None:
            self._warn("Ишчи аввал «✍ Имзо қўйиш» билан имзо қўйсин.")
            return

        passport = self._review.edited()
        gender = "Женский" if passport.gender == Gender.FEMALE else "Мужской"
        photo = self._c.read_image(self._photo.path)
        start_date = self._start.date().toPython()

        self._run.setEnabled(False)
        self._progress.start("3 та ҳужжат тайёрланяпти…")
        run_async(
            self._c.generate, passport=passport,
            ud_number=self._ud_number.text().strip(),
            dolzhnost=self._dolzhnost.currentText().strip(),
            gender=gender, start_date=start_date, photo=photo,
            signature=self._signature,
            on_success=self._done, on_error=self._failed)

    def _done(self, results) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        from src.ui.widgets.save_to import ask_save_dir

        saved = [r.saved for r in results]
        ask_save_dir(self, saved)
        self._passport.clear()
        self._photo.clear()
        self._review.reset()
        self._signature = None
        self._sign_state.setText("Имзо: ҳали қўйилмаган ⚠️")
        names = ", ".join(p.name for p in saved)
        self._status.setText(f"✅ Тайёр (3 та): {names}")

    def _failed(self, error: Exception) -> None:
        self._progress.finish()
        self._run.setEnabled(True)
        message = getattr(error, "message", None) or str(error)
        self._status.setText(f"❌ {message}")

    def _open_folder(self) -> None:
        from src.config import paths
        from src.ui.views.settings_view import _open_folder

        folder = paths.output_dir() / "alliance"
        folder.mkdir(parents=True, exist_ok=True)
        _open_folder(folder)

    def _warn(self, message: str) -> None:
        self._status.setText(f"⚠️ {message}")

    def reset(self) -> None:
        pass
