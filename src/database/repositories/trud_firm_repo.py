"""TrudFirm persistence. The only code touching the ``trud_firms`` table."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from src.database.connection import Database
from src.domain.enums import CompanyStatus
from src.domain.trud_firm import TrudFirm


def _row(r: sqlite3.Row) -> TrudFirm:
    return TrudFirm(
        id=UUID(r["id"]), name=r["name"], internal_code=r["internal_code"],
        trud_template_path=Path(r["trud_template_path"]),
        uved_template_path=Path(r["uved_template_path"]),
        status=CompanyStatus(r["status"]), notes=r["notes"],
    )


class TrudFirmRepository:
    def __init__(self, db: Database) -> None:
        self._conn = db.connection

    def upsert(self, f: TrudFirm) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO trud_firms (id, name, internal_code, trud_template_path,
                    uved_template_path, status, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, internal_code=excluded.internal_code,
                    trud_template_path=excluded.trud_template_path,
                    uved_template_path=excluded.uved_template_path,
                    status=excluded.status, notes=excluded.notes, updated_at=excluded.updated_at
                """,
                (str(f.id), f.name, f.internal_code, str(f.trud_template_path),
                 str(f.uved_template_path), f.status.value, f.notes, now, now),
            )

    def by_internal_code(self, code: str) -> TrudFirm | None:
        row = self._conn.execute(
            "SELECT * FROM trud_firms WHERE internal_code = ?", (code,)
        ).fetchone()
        return _row(row) if row else None

    def list_active(self) -> list[TrudFirm]:
        rows = self._conn.execute(
            "SELECT * FROM trud_firms WHERE status = ? ORDER BY name",
            (CompanyStatus.ACTIVE.value,),
        ).fetchall()
        return [_row(r) for r in rows]

    def archive(self, firm_id: UUID) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                "UPDATE trud_firms SET status=?, updated_at=? WHERE id=?",
                (CompanyStatus.ARCHIVED.value, now, str(firm_id)),
            )

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS n FROM trud_firms").fetchone()["n"])
