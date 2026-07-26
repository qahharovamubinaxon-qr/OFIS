"""Backup / restore of everything the user has entered (Phase 11).

A backup is one ZIP containing the SQLite database (checkpointed so the single
``ofis.db`` file is complete) plus every user-imported template. Restore is
two-step on purpose: the ZIP is *staged* into ``restore_pending/`` while the
app is running (the DB file is locked and mid-transaction on Windows), and
applied atomically at the next startup **before** the database is opened.
"""

from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from src.common.errors import ValidationError
from src.common.logging import get_logger
from src.config import paths

log = get_logger(__name__)

_DB_NAME = "ofis.db"
_TEMPLATES_PREFIX = "templates/"
_PENDING_DIR = "restore_pending"


class BackupService:
    """Create backup ZIPs and stage restores.

    ``db_connection`` is optional: when provided (the running app) the WAL is
    checkpointed first so the copied ``ofis.db`` contains every committed row.
    """

    def __init__(self, db_connection: sqlite3.Connection | None = None) -> None:
        self._conn = db_connection

    # -- create --------------------------------------------------------
    def create_backup(self, dest_dir: Path | None = None) -> Path:
        """Zip the DB + user templates into ``dest_dir`` (default: backups dir).

        Returns the path of the created ZIP."""
        if self._conn is not None:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            except sqlite3.Error as exc:  # non-fatal: WAL merge is best-effort
                log.warning("WAL checkpoint failed before backup: %s", exc)

        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        target_dir = dest_dir or paths.backups_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"OFIS_backup_{stamp}.zip"

        db_file = paths.database_path()
        if not db_file.exists():
            raise ValidationError("Database file not found", context={"path": str(db_file)})

        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(db_file, _DB_NAME)
            templates = paths.user_templates_dir()
            for file in sorted(templates.rglob("*")):
                if file.is_file():
                    zf.write(file, _TEMPLATES_PREFIX + file.relative_to(templates).as_posix())
        log.info("Backup created: %s", target)
        return target

    # -- restore -------------------------------------------------------
    @staticmethod
    def stage_restore(zip_path: Path) -> None:
        """Validate the ZIP and unpack it into ``restore_pending/``.

        The actual swap happens on next startup (``apply_pending_restore``),
        when nothing holds the DB open."""
        if not zipfile.is_zipfile(zip_path):
            raise ValidationError("Not a valid backup ZIP", context={"path": str(zip_path)})
        pending = paths.data_dir() / _PENDING_DIR
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            if _DB_NAME not in names:
                raise ValidationError(
                    "ZIP is not an OFIS backup (ofis.db missing)",
                    context={"path": str(zip_path)},
                )
            for name in names:  # zip-slip guard
                dest = (pending / name).resolve()
                if not str(dest).startswith(str(pending.resolve())):
                    raise ValidationError("Unsafe path in archive", context={"entry": name})
            if pending.exists():
                shutil.rmtree(pending)
            pending.mkdir(parents=True)
            zf.extractall(pending)
        log.info("Restore staged from %s", zip_path)

    @staticmethod
    def apply_pending_restore() -> bool:
        """Called at startup BEFORE the database opens. Returns True if a
        staged restore was applied. The current DB is saved to backups/ first,
        so even a restore can be undone."""
        pending = paths.data_dir() / _PENDING_DIR
        staged_db = pending / _DB_NAME
        if not staged_db.exists():
            if pending.exists():  # half-staged leftovers — clear them
                shutil.rmtree(pending, ignore_errors=True)
            return False

        current = paths.database_path()
        if current.exists():
            stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            shutil.copyfile(current, paths.backups_dir() / f"pre_restore_{stamp}.db")
            # stale WAL/SHM would corrupt the restored DB — remove them
            for suffix in ("-wal", "-shm"):
                side = current.with_name(current.name + suffix)
                if side.exists():
                    side.unlink()
        shutil.move(str(staged_db), str(current))

        staged_templates = pending / "templates"
        if staged_templates.is_dir():
            shutil.copytree(staged_templates, paths.user_templates_dir(), dirs_exist_ok=True)
        shutil.rmtree(pending, ignore_errors=True)
        log.info("Backup restored (DB + user templates)")
        return True
