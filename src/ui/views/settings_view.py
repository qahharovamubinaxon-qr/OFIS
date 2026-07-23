"""Settings screen — Gemini key, theme, language, output folder.

The Gemini key is stored via SettingsService (the DB); entering it makes AI mode
available without a restart of the OCR layer on next generation build. Theme
applies live; language change asks for a restart (view strings rebuild on start).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import constants, paths
from src.config.settings_service import SettingsService


class SettingsView(QWidget):
    def __init__(self, settings: SettingsService, on_theme_change=None) -> None:
        super().__init__()
        self._settings = settings
        self._on_theme_change = on_theme_change

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("Sozlamalar / Настройки")
        title.setObjectName("viewTitle")
        root.addWidget(title)

        form = QFormLayout()
        form.setVerticalSpacing(12)

        # Gemini key
        key_row = QHBoxLayout()
        self._key = QLineEdit(str(self._settings.get("ai.gemini_key", "") or ""))
        self._key.setEchoMode(QLineEdit.EchoMode.Password)
        self._key.setPlaceholderText("AIza…")
        save_key = QPushButton("Saqlash")
        save_key.clicked.connect(self._save_key)
        key_row.addWidget(self._key, stretch=1)
        key_row.addWidget(save_key)
        form.addRow("Gemini API kalit:", key_row)

        # theme
        self._theme = QComboBox()
        self._theme.addItems(constants.SUPPORTED_THEMES)
        self._theme.setCurrentText(self._settings.theme)
        self._theme.currentTextChanged.connect(self._save_theme)
        form.addRow("Mavzu / Theme:", self._theme)

        # language
        self._lang = QComboBox()
        self._lang.addItems(constants.SUPPORTED_LANGUAGES)
        self._lang.setCurrentText(self._settings.language)
        self._lang.currentTextChanged.connect(self._save_lang)
        form.addRow("Til / Язык:", self._lang)

        root.addLayout(form)

        out = QLabel(f"Chiqish papkasi: {paths.output_dir()}")
        out.setStyleSheet("color:#8a94a3;")
        out.setWordWrap(True)
        root.addWidget(out)
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
