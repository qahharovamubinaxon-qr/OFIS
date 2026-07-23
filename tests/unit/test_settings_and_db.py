"""Database migration + settings service round-trip (real SQLite, temp file)."""

from __future__ import annotations

from pathlib import Path

from src.config.settings_service import SettingsService
from src.database.connection import Database
from src.database.repositories.settings_repo import SettingsRepository


def _service(tmp_path: Path) -> tuple[SettingsService, Database]:
    db = Database(tmp_path / "test.db")
    db.migrate()
    return SettingsService(SettingsRepository(db)), db


def test_migration_is_idempotent(tmp_path: Path) -> None:
    db = Database(tmp_path / "m.db")
    first = db.migrate()
    second = db.migrate()
    assert first >= 1  # at least 0001 applied
    assert second == 0  # nothing re-applied
    db.close()


def test_settings_defaults_before_write(tmp_path: Path) -> None:
    svc, db = _service(tmp_path)
    assert svc.theme == "dark"
    assert svc.language == "ru"
    assert svc.get_float("ocr.confidence_threshold") == 0.90
    db.close()


def test_settings_persist_and_type(tmp_path: Path) -> None:
    svc, db = _service(tmp_path)
    svc.set("theme", "light")
    svc.set("ocr.confidence_threshold", 0.8)
    svc.set("pdf.open_after_generation", False)
    assert svc.theme == "light"
    assert svc.get_float("ocr.confidence_threshold") == 0.8
    assert svc.get_bool("pdf.open_after_generation") is False
    db.close()


def test_invalid_language_falls_back(tmp_path: Path) -> None:
    svc, db = _service(tmp_path)
    svc.set("language", "fr")  # unsupported
    assert svc.language == "ru"
    db.close()
