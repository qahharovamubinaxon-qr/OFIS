"""SQLite connection + forward-only migration runner.

WAL mode + enforced foreign keys. Migrations are ordered ``NNNN_name.sql`` files
in ``migrations/``; each is applied once inside a transaction and recorded in
``schema_migrations``. Applying is idempotent and safe to run on every startup.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from src.common.errors import MigrationError
from src.common.logging import get_logger

log = get_logger(__name__)

_MIGRATION_RE = re.compile(r"^(\d{4})_.+\.sql$")


def _migrations_dir() -> Path:
    """Where the ``*.sql`` migrations live — resolved for both dev and EXE.

    In development they sit next to this file. Under PyInstaller the source tree
    is inside the archive (so ``__file__``/migrations does not exist on disk), and
    the ``.sql`` files are bundled beside resources/templates under ``app_root``.
    """
    local = Path(__file__).resolve().parent / "migrations"
    if local.is_dir() and any(local.glob("*.sql")):
        return local
    from src.config import paths

    return paths.app_root() / "migrations"


class Database:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA busy_timeout = 5000;")

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def migrate(self, migrations_dir: Path | None = None) -> int:
        """Apply any pending migrations. Returns how many were applied."""
        directory = migrations_dir or _migrations_dir()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {r["version"] for r in self._conn.execute("SELECT version FROM schema_migrations")}

        count = 0
        for path in sorted(directory.glob("*.sql")):
            m = _MIGRATION_RE.match(path.name)
            if not m:
                continue
            version = int(m.group(1))
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            try:
                with self._conn:  # transaction
                    self._conn.executescript(sql)
                    self._conn.execute(
                        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                        (version, datetime.now().isoformat(timespec="seconds")),
                    )
            except sqlite3.Error as exc:
                raise MigrationError(
                    f"Migration {path.name} failed", context={"error": str(exc)}
                ) from exc
            log.info("Applied migration %s", path.name)
            count += 1
        return count

    def close(self) -> None:
        self._conn.close()
