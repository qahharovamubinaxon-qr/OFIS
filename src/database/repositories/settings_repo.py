"""Key/value settings persistence. The only thing that talks to the settings
table. Values are stored as JSON text and typed on read by the service above.
"""

from __future__ import annotations

from datetime import datetime

from src.database.connection import Database


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self._conn = db.connection

    def get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, value, datetime.now().isoformat(timespec="seconds")),
            )

    def all(self) -> dict[str, str]:
        return {r["key"]: r["value"] for r in self._conn.execute("SELECT key, value FROM settings")}
