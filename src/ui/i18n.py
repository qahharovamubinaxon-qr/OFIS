"""Runtime translations. Loads ``resources/i18n/<lang>.json`` and resolves keys
with an English/last-resort fallback. Language switches without a restart: views
call :meth:`Translator.tr` on (re)render and the window re-renders on change.
"""

from __future__ import annotations

import json
from functools import lru_cache

from src.common.logging import get_logger
from src.config import constants, paths

log = get_logger(__name__)


@lru_cache(maxsize=len(constants.SUPPORTED_LANGUAGES))
def _load(lang: str) -> dict[str, str]:
    path = paths.resources_dir() / "i18n" / f"{lang}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not load i18n %s: %s", lang, exc)
        return {}


class Translator:
    def __init__(self, language: str = constants.DEFAULT_LANGUAGE) -> None:
        self._lang = language

    @property
    def language(self) -> str:
        return self._lang

    def set_language(self, language: str) -> None:
        if language in constants.SUPPORTED_LANGUAGES:
            self._lang = language

    def tr(self, key: str, default: str | None = None) -> str:
        table = _load(self._lang)
        if key in table:
            return table[key]
        fallback = _load(constants.DEFAULT_LANGUAGE)
        return fallback.get(key, default if default is not None else key)
