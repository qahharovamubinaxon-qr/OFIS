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


def test_two_threads_reading_at_once_do_not_trip_sqlite(tmp_path: Path) -> None:
    """The office's startup crash — «bad parameter or other API misuse».

    The window read the theme on the main thread just as the housekeeping
    sweep read a setting on its own thread, both on the one shared connection.
    With a connection per thread this must run clean under real contention.
    """
    import threading

    svc, db = _service(tmp_path)
    svc.set("theme", "light")
    errors: list[Exception] = []

    def hammer() -> None:
        try:
            for _ in range(200):
                assert svc.theme == "light"
                assert svc.language == "ru"   # a second read, different key
        except Exception as exc:  # noqa: BLE001 - the whole point is to catch it
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent DB access raised: {errors[:3]}"
    db.close()


def test_a_write_from_another_thread_is_seen(tmp_path: Path) -> None:
    """Per-thread connections still share the one file: a value written on one
    thread is read back on another (WAL + committed transactions)."""
    import threading

    svc, db = _service(tmp_path)

    def writer() -> None:
        svc.set("theme", "light")

    t = threading.Thread(target=writer)
    t.start()
    t.join()

    assert svc.theme == "light"      # read on the main thread's own connection
    db.close()
