"""Backup → stage → apply round-trip on an isolated data dir."""

from __future__ import annotations

import sqlite3
import tempfile

import pytest

from src.config import paths
from src.services.backup_service import BackupService


@pytest.fixture()
def isolated_data_dir(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", tempfile.mkdtemp())
    paths.data_dir.cache_clear()
    yield paths.data_dir()
    paths.data_dir.cache_clear()


def _make_db(marker: str) -> None:
    conn = sqlite3.connect(paths.database_path())
    conn.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
    conn.execute("DELETE FROM t")
    conn.execute("INSERT INTO t (v) VALUES (?)", (marker,))
    conn.commit()
    conn.close()


def _read_marker() -> str:
    conn = sqlite3.connect(paths.database_path())
    value = conn.execute("SELECT v FROM t").fetchone()[0]
    conn.close()
    return str(value)


def test_backup_restore_roundtrip(isolated_data_dir) -> None:
    _make_db("original")
    (paths.user_templates_dir() / "firm_x").mkdir(parents=True)
    (paths.user_templates_dir() / "firm_x" / "template.pdf").write_bytes(b"PDF")

    backup = BackupService().create_backup()
    assert backup.exists() and backup.suffix == ".zip"

    # user then loses/changes everything
    _make_db("changed")
    (paths.user_templates_dir() / "firm_x" / "template.pdf").unlink()

    BackupService.stage_restore(backup)
    assert (paths.data_dir() / "restore_pending" / "ofis.db").exists()

    assert BackupService.apply_pending_restore() is True
    assert _read_marker() == "original"
    assert (paths.user_templates_dir() / "firm_x" / "template.pdf").read_bytes() == b"PDF"
    assert not (paths.data_dir() / "restore_pending").exists()
    # the pre-restore DB was kept, so even a wrong restore is reversible
    assert list(paths.backups_dir().glob("pre_restore_*.db"))


def test_apply_without_staged_restore_is_noop(isolated_data_dir) -> None:
    _make_db("keep")
    assert BackupService.apply_pending_restore() is False
    assert _read_marker() == "keep"


def test_stage_rejects_foreign_zip(isolated_data_dir, tmp_path) -> None:
    import zipfile

    bad = tmp_path / "other.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("readme.txt", "not an ofis backup")
    from src.common.errors import ValidationError

    with pytest.raises(ValidationError):
        BackupService.stage_restore(bad)
