"""Filesystem locations, resolved the Windows way.

Program files stay read-only; all mutable data (settings DB, logs, cache,
backups, output, archive) lives under ``%LOCALAPPDATA%\\OFIS`` so the app runs
without admin rights and survives an EXE update untouched. On non-Windows dev
machines (this repo is developed on Linux) it falls back to an XDG-style path so
the app is runnable everywhere for testing.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

APP_NAME = "OFIS"


@lru_cache(maxsize=1)
def app_root() -> Path:
    """Directory the application is installed/run from (read-only at runtime)."""
    if getattr(sys, "frozen", False):  # PyInstaller one-file
        return Path(sys.executable).resolve().parent
    # repo root = two levels up from this file (src/config/paths.py -> repo)
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def data_dir() -> Path:
    """Writable per-user data directory. Created on first access."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        root = base / APP_NAME
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        root = base / APP_NAME.lower()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    return _sub("logs")


def cache_dir() -> Path:
    return _sub("cache")


def temp_dir() -> Path:
    return _sub("temp")


def backups_dir() -> Path:
    return _sub("backups")


def output_dir() -> Path:
    return _sub("output")


def archive_dir() -> Path:
    return _sub("archive")


def database_path() -> Path:
    return data_dir() / "ofis.db"


def resources_dir() -> Path:
    """Bundled, read-only resources (qss, i18n, icons, fonts)."""
    return app_root() / "resources"


def templates_dir() -> Path:
    """Bundled company PDF templates + their mappings."""
    return app_root() / "templates"
