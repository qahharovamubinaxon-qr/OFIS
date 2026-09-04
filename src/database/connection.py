"""SQLite connection + forward-only migration runner.

WAL mode + enforced foreign keys. Migrations are ordered ``NNNN_name.sql`` files
in ``migrations/``; each is applied once inside a transaction and recorded in
``schema_migrations``. Applying is idempotent and safe to run on every startup.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from src.common.errors import MigrationError
from src.common.logging import get_logger

log = get_logger(__name__)

_MIGRATION_RE = re.compile(r"^(\d{4})_.+\.sql$")


class _ThreadLocalConnection:
    """One real SQLite connection per thread, behind one shared object.

    The app has always kept a SINGLE ``sqlite3.connect(..., check_same_thread=
    False)`` and handed it to every repository. That is unsafe: the desktop
    window, the Telegram bot, the Mini-App server, the tunnel and the startup
    housekeeping sweep all run on their own threads, and two of them touching
    the one connection at the same moment makes SQLite raise «bad parameter or
    other API misuse» (SQLITE_MISUSE) — a crash the office hit at random,
    once the startup sweep read a setting just as the window read the theme.

    SQLite itself is happy with many connections to one file (WAL + a busy
    timeout handle the contention). So each thread gets its OWN connection,
    opened on first use, while the repositories keep holding this one object
    and calling ``.execute`` / ``with conn:`` exactly as before.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            self._local.conn = conn
            with self._lock:
                self._all.append(conn)
        return conn

    # the surface the repositories and the migrator actually use
    def execute(self, *args, **kwargs):
        return self._conn().execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        return self._conn().executemany(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        return self._conn().executescript(*args, **kwargs)

    def commit(self) -> None:
        self._conn().commit()

    def rollback(self) -> None:
        self._conn().rollback()

    def __enter__(self):
        # ``with conn:`` is a transaction on THIS thread's own connection
        return self._conn().__enter__()

    def __exit__(self, *exc):
        return self._conn().__exit__(*exc)

    def close_all(self) -> None:
        import contextlib

        with self._lock:
            for conn in self._all:
                with contextlib.suppress(sqlite3.Error):
                    conn.close()
            self._all.clear()


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
        # one connection per thread, so the window, the bot, the Mini-App and
        # the startup sweep never share a statement and never trip SQLITE_MISUSE
        self._conn = _ThreadLocalConnection(str(db_path))

    @property
    def connection(self) -> _ThreadLocalConnection:
        return self._conn

    def migrate(self, migrations_dir: Path | None = None) -> int:
        """Apply any pending migrations. Returns how many were applied."""
        directory = migrations_dir or _migrations_dir()
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {r["version"] for r in
                   self._conn.execute("SELECT version FROM schema_migrations")}

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
        self._conn.close_all()
