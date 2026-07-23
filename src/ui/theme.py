"""Applies a Qt stylesheet (light/dark) to the running app at runtime.

Themes are plain ``.qss`` files in ``resources/qss`` so designers can tweak them
without touching Python. Switching is instant — no restart.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from src.common.logging import get_logger
from src.config import constants, paths

log = get_logger(__name__)


def apply_theme(app: QApplication, theme: str) -> None:
    name = theme if theme in constants.SUPPORTED_THEMES else constants.DEFAULT_THEME
    qss_path = paths.resources_dir() / "qss" / f"{name}.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
        log.info("Applied theme: %s", name)
    else:
        log.warning("Theme file missing: %s", qss_path)
