"""Profession persistence. The only code that touches the ``professions`` table."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from uuid import UUID

from src.database.connection import Database
from src.domain.enums import CompanyStatus
from src.domain.profession import Profession


def _row(r: sqlite3.Row) -> Profession:
    return Profession(
        id=UUID(r["id"]), name=r["name"], note=r["note"], grade=r["grade"],
        status=CompanyStatus(r["status"]),
    )


class ProfessionRepository:
    def __init__(self, db: Database) -> None:
        self._conn = db.connection

    def add(self, p: Profession, sort_order: int = 0) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                "INSERT INTO professions (id, name, note, grade, status, sort_order, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (str(p.id), p.name, p.note, p.grade, p.status.value, sort_order, now),
            )

    def list_active(self) -> list[Profession]:
        rows = self._conn.execute(
            "SELECT * FROM professions WHERE status = ? ORDER BY sort_order, name",
            (CompanyStatus.ACTIVE.value,),
        ).fetchall()
        return [_row(r) for r in rows]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS n FROM professions").fetchone()["n"])
