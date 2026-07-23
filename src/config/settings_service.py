"""Centralized settings, typed and validated, backed by the settings table.

Every module reads configuration through this service (never through direct DB
access or hardcoded constants). Unknown keys fall back to documented defaults,
so adding a new setting never breaks an existing install.
"""

from __future__ import annotations

import json

from src.config import constants
from src.database.repositories.settings_repo import SettingsRepository

_DEFAULTS: dict[str, object] = {
    "language": constants.DEFAULT_LANGUAGE,
    "theme": constants.DEFAULT_THEME,
    "ai.primary_provider": "gemini",
    "ai.secondary_provider": "openai",
    "ai.retries": constants.DEFAULT_AI_RETRIES,
    "ocr.confidence_threshold": constants.DEFAULT_CONFIDENCE_THRESHOLD,
    "ocr.timeout_s": constants.DEFAULT_OCR_TIMEOUT_S,
    "pdf.open_after_generation": True,
    "window.remember_geometry": True,
}


class SettingsService:
    def __init__(self, repo: SettingsRepository) -> None:
        self._repo = repo

    def get(self, key: str, default: object | None = None) -> object:
        raw = self._repo.get(key)
        if raw is None:
            return _DEFAULTS.get(key, default)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def get_str(self, key: str) -> str:
        return str(self.get(key))

    def get_int(self, key: str) -> int:
        return int(self.get(key))  # type: ignore[arg-type]

    def get_float(self, key: str) -> float:
        return float(self.get(key))  # type: ignore[arg-type]

    def get_bool(self, key: str) -> bool:
        return bool(self.get(key))

    def set(self, key: str, value: object) -> None:
        self._repo.set(key, json.dumps(value, ensure_ascii=False))

    @property
    def language(self) -> str:
        lang = self.get_str("language")
        return lang if lang in constants.SUPPORTED_LANGUAGES else constants.DEFAULT_LANGUAGE

    @property
    def theme(self) -> str:
        theme = self.get_str("theme")
        return theme if theme in constants.SUPPORTED_THEMES else constants.DEFAULT_THEME
