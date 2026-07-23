"""Structured logging → rotating file (AppData) + console.

DB logging (the ``logs`` table) is attached in a later phase via a handler that
the database layer registers; keeping it out of here preserves the dependency
rule (``common`` must not import ``database``).
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from src.config import constants, paths

_CONFIGURED = False

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Idempotently set up root logging. Safe to call more than once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    lvl = (level or os.environ.get("OFIS_LOG_LEVEL", "INFO")).upper()
    root = logging.getLogger()
    root.setLevel(lvl)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)

    log_file = paths.logs_dir() / "ofis.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(file_handler)

    _CONFIGURED = True
    logging.getLogger(__name__).info(
        "Logging initialized (level=%s, version=%s)", lvl, constants.APP_VERSION
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
