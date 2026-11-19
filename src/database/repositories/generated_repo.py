"""Persistence for the generated-documents log (Dashboard / Archive / Search)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import uuid4

from src.database.connection import Database


@dataclass(frozen=True)
class GeneratedRecord:
    id: str
    company_name: str
    surname: str
    full_name: str
    citizenship: str
    reg_number: int
    pdf_path: str
    form_date: str
    created_at: str


def _row(r: sqlite3.Row) -> GeneratedRecord:
    return GeneratedRecord(
        id=r["id"], company_name=r["company_name"], surname=r["surname"],
        full_name=r["full_name"], citizenship=r["citizenship"] or "",
        reg_number=r["reg_number"], pdf_path=r["pdf_path"],
        form_date=r["form_date"], created_at=r["created_at"],
    )


class GeneratedRepository:
    def __init__(self, db: Database) -> None:
        self._conn = db.connection

    def add(
        self, *, company_id: str | None, company_name: str, surname: str, full_name: str,
        citizenship: str, reg_number: int, pdf_path: str, form_date: date,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO generated_documents (id, company_id, company_name, surname,
                   full_name, citizenship, reg_number, pdf_path, form_date, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid4()), company_id, company_name, surname, full_name, citizenship,
                 reg_number, pdf_path, form_date.isoformat(),
                 datetime.now().isoformat(timespec="seconds")),
            )

    def recent(self, limit: int = 20) -> list[GeneratedRecord]:
        rows = self._conn.execute(
            "SELECT * FROM generated_documents ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row(r) for r in rows]

    def search(self, query: str, limit: int = 100) -> list[GeneratedRecord]:
        like = f"%{query.strip()}%"
        rows = self._conn.execute(
            """SELECT * FROM generated_documents
               WHERE surname LIKE ? OR full_name LIKE ? OR CAST(reg_number AS TEXT) LIKE ?
               ORDER BY created_at DESC LIMIT ?""",
            (like, like, like, limit),
        ).fetchall()
        return [_row(r) for r in rows]

    def count_total(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) n FROM generated_documents").fetchone()["n"])

    def count_today(self) -> int:
        today = date.today().isoformat()
        return int(self._conn.execute(
            "SELECT COUNT(*) n FROM generated_documents WHERE substr(created_at,1,10)=?", (today,)
        ).fetchone()["n"])

    def busiest_day(self, days: int = 14) -> int:
        """The most documents made on any one of the last ``days`` days.

        The home screen's ring needs something true to be a fraction OF. A
        made-up daily target would make the ring a decoration; the office's
        own busiest recent day is a real mark, and it answers the question
        they actually ask in the morning — «бугун қандай кетяпти?».

        Returns 0 when nothing has been made in that window, and the caller
        decides what an empty ring means.
        """
        window = max(1, int(days))
        first = (date.today() - timedelta(days=window - 1)).isoformat()
        row = self._conn.execute(
            """SELECT MAX(n) m FROM (
                   SELECT COUNT(*) n FROM generated_documents
                   WHERE substr(created_at,1,10) >= ?
                   GROUP BY substr(created_at,1,10))""",
            (first,),
        ).fetchone()
        return int(row["m"] or 0)
