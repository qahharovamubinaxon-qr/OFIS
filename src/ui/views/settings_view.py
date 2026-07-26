"""Settings screen — Gemini key, theme, language, output folder.

The Gemini key is stored via SettingsService (the DB); entering it makes AI mode
available without a restart of the OCR layer on next generation build. Theme
applies live; language change asks for a restart (view strings rebuild on start).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.common.errors import OfisError
from src.config import constants, paths
from src.config.settings_service import SettingsService
from src.services.backup_service import BackupService
from src.ui.widgets.card import Card


def _right(widget: QWidget) -> QHBoxLayout:
    """Push a single control to the right edge of its card."""
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(widget)
    return row


class SettingsView(QWidget):
    def __init__(
        self,
        settings: SettingsService,
        on_theme_change=None,
        backup: BackupService | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._on_theme_change = on_theme_change
        self._backup = backup or BackupService()

        page = QVBoxLayout(self)
        page.setContentsMargins(28, 24, 28, 16)
        page.setSpacing(14)

        title = QLabel("Sozlamalar / Настройки")
        title.setObjectName("viewTitle")
        page.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        root = QVBoxLayout(holder)
        root.setContentsMargins(0, 0, 10, 0)
        root.setSpacing(16)
        scroll.setWidget(holder)
        page.addWidget(scroll, stretch=1)

        # -- AI ---------------------------------------------------------
        ai = Card("🤖", "Sun'iy intellekt",
                  "Hujjatlarni o'qish, tarjima va matn tayyorlash uchun Gemini kaliti.")
        key_row = QHBoxLayout()
        self._key = QLineEdit(str(self._settings.get("ai.gemini_key", "") or ""))
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("AIza…")
        save_key = QPushButton("Saqlash")
        save_key.setObjectName("primaryButton")
        save_key.clicked.connect(self._save_key)
        key_row.addWidget(QLabel("Gemini API kalit:"))
        key_row.addWidget(self._key, stretch=1)
        key_row.addWidget(save_key)
        ai.add(key_row)
        root.addWidget(ai)

        # -- appearance --------------------------------------------------
        look = Card("🎨", "Ko'rinish", "Mavzu darhol, til qayta ishga tushirgach.")
        look_form = look.form()
        self._theme = QComboBox()
        self._theme.addItems(constants.SUPPORTED_THEMES)
        self._theme.setCurrentText(self._settings.theme)
        self._theme.currentTextChanged.connect(self._save_theme)
        look_form.addRow("Mavzu / Theme:", self._theme)
        self._lang = QComboBox()
        self._lang.addItems(constants.SUPPORTED_LANGUAGES)
        self._lang.setCurrentText(self._settings.language)
        self._lang.currentTextChanged.connect(self._save_lang)
        look_form.addRow("Til / Язык:", self._lang)
        root.addWidget(look)

        # -- доверенность counters ---------------------------------------
        from src.services.dover_service import (
            DEFAULT_REESTR_NEXT, DEFAULT_SERIES_NEXT, DEFAULT_SERIES_PREFIX,
            DEFAULT_TARIF, KEY_REESTR_NEXT, KEY_SERIES_NEXT, KEY_SERIES_PREFIX,
            KEY_TARIF,
        )

        dover = Card("📜", "Доверенность · Согласие",
                     "Бланк серияси ва реестр рақами ҳар ҳужжатда автомат +1 бўлади.")
        dv = dover.form()
        self._dv_prefix = QLineEdit(str(
            self._settings.get(KEY_SERIES_PREFIX, DEFAULT_SERIES_PREFIX)
            or DEFAULT_SERIES_PREFIX))
        self._dv_series = QLineEdit(str(
            self._settings.get(KEY_SERIES_NEXT, DEFAULT_SERIES_NEXT) or DEFAULT_SERIES_NEXT))
        self._dv_reestr = QLineEdit(str(
            self._settings.get(KEY_REESTR_NEXT, DEFAULT_REESTR_NEXT) or DEFAULT_REESTR_NEXT))
        self._dv_tarif = QLineEdit(str(
            self._settings.get(KEY_TARIF, DEFAULT_TARIF) or DEFAULT_TARIF))
        dv.addRow("Бланк серияси (префикс):", self._dv_prefix)
        dv.addRow("Кейинги бланк рақами:", self._dv_series)
        dv.addRow("Кейинги реестр №:", self._dv_reestr)
        dv.addRow("Тариф (руб.):", self._dv_tarif)
        save_dv = QPushButton("Saqlash")
        save_dv.setObjectName("primaryButton")
        save_dv.clicked.connect(self._save_dover)
        dover.add(_right(save_dv))
        root.addWidget(dover)

        # -- telegram bot -------------------------------------------------
        from src.controllers.telegram_bot import KEY_PASSWORD, KEY_TOKEN

        tg_card = Card("📱", "Telegram bot",
                       "Telefondan PDF tayyorlash — kompyuter va OFIS ochiq turishi kerak.")
        tg = tg_card.form()
        self._tg_token = QLineEdit(str(self._settings.get(KEY_TOKEN, "") or ""))
        self._tg_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._tg_token.setPlaceholderText("123456789:AA… (@BotFather'дан)")
        self._tg_parol = QLineEdit(str(self._settings.get(KEY_PASSWORD, "") or ""))
        self._tg_parol.setPlaceholderText("масалан: ofis2026")
        tg.addRow("Бот токени:", self._tg_token)
        tg.addRow("Парол:", self._tg_parol)
        save_tg = QPushButton("Saqlash")
        save_tg.setObjectName("primaryButton")
        save_tg.clicked.connect(self._save_telegram)
        tg_card.add(_right(save_tg))
        tg_card.note(
            "@BotFather → /newbot → tokenni shu yerga kiriting. Telefondan botga: "
            "/start PAROL. Token kiritilgach dasturni qayta oching."
        )
        root.addWidget(tg_card)

        # -- backup / restore ---------------------------------------------
        bk = Card("💾", "Zaxira nusxa",
                  "Butun baza (firmalar, manzillar, hisoblagichlar, arxiv) + shablonlar.")
        bk_row = QHBoxLayout()
        make_bk = QPushButton("💾  Zaxira yaratish (ZIP)")
        make_bk.clicked.connect(self._create_backup)
        restore_bk = QPushButton("📥  Zaxiradan tiklash")
        restore_bk.clicked.connect(self._restore_backup)
        bk_row.addWidget(make_bk)
        bk_row.addWidget(restore_bk)
        bk_row.addStretch(1)
        bk.add(bk_row)
        bk.note("Yangi kompyuterga o'tishda yoki har oy bir marta zaxira oling.")
        root.addWidget(bk)

        # -- folders --------------------------------------------------------
        folders = Card("📁", "Papkalar", "")
        folders.note(f"Chiqish papkasi:  {paths.output_dir()}")
        folders.note(f"Ma'lumotlar:  {paths.data_dir()}")
        root.addWidget(folders)

        root.addStretch(1)

    def _save_key(self) -> None:
        self._settings.set("ai.gemini_key", self._key.text().strip())
        QMessageBox.information(self, "OK", "Gemini kaliti saqlandi. Keyingi PDF'da ishlaydi.")

    def _save_theme(self, theme: str) -> None:
        self._settings.set("theme", theme)
        if self._on_theme_change:
            self._on_theme_change(theme)

    def _save_lang(self, lang: str) -> None:
        self._settings.set("language", lang)
        QMessageBox.information(self, "OK", "Til saqlandi. Qayta ishga tushiring / Restart to apply.")

    def _save_dover(self) -> None:
        from src.services.dover_service import (
            KEY_REESTR_NEXT, KEY_SERIES_NEXT, KEY_SERIES_PREFIX, KEY_TARIF,
        )

        try:
            series = int(self._dv_series.text().strip())
            reestr = int(self._dv_reestr.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Xato", "Бланк рақами ва реестр № — фақат рақам.")
            return
        self._settings.set(KEY_SERIES_PREFIX, self._dv_prefix.text().strip() or "77 АВ")
        self._settings.set(KEY_SERIES_NEXT, series)
        self._settings.set(KEY_REESTR_NEXT, reestr)
        self._settings.set(KEY_TARIF, self._dv_tarif.text().strip() or "1500")
        QMessageBox.information(self, "OK", "Доверенность рақамлари сақланди.")

    def _save_telegram(self) -> None:
        from src.controllers.telegram_bot import KEY_PASSWORD, KEY_TOKEN

        self._settings.set(KEY_TOKEN, self._tg_token.text().strip())
        self._settings.set(KEY_PASSWORD, self._tg_parol.text().strip())
        QMessageBox.information(
            self, "OK",
            "Telegram sozlamalari saqlandi.\nDasturni yopib qayta oching — "
            "bot shunda ishga tushadi.")

    # -- backup / restore ----------------------------------------------
    def _create_backup(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Zaxira qayerga saqlansin?", str(paths.desktop_dir())
        )
        if not folder:
            return
        try:
            target = self._backup.create_backup(Path(folder))
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        QMessageBox.information(self, "Tayyor", f"Zaxira nusxa yaratildi:\n{target}")

    def _restore_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Zaxira ZIP faylini tanlang", str(paths.desktop_dir()),
            "OFIS backup (*.zip)",
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Tasdiqlash",
            "Joriy ma'lumotlar zaxiradagi bilan ALMASHTIRILADI.\n"
            "(Hozirgi baza avval backups/ papkasiga saqlab qo'yiladi.)\n\nDavom etamizmi?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            BackupService.stage_restore(Path(path))
        except OfisError as exc:
            QMessageBox.warning(self, "Xato", exc.message)
            return
        QMessageBox.information(
            self, "Tayyor",
            "Zaxira qabul qilindi.\nDasturni YOPIB QAYTA OCHING — "
            "ma'lumotlar shunda tiklanadi.",
        )
