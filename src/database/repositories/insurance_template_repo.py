"""ОСАГО template persistence. The only code touching that table."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from src.database.connection import Database
from src.domain.enums import CompanyStatus
from src.domain.insurance_template import InsuranceTemplate


def _row(r: sqlite3.Row) -> InsuranceTemplate:
    return InsuranceTemplate(
        id=UUID(r["id"]), name=r["name"], internal_code=r["internal_code"],
        insurer=r["insurer"] or "", firm=r["firm"] or "",
        template_path=Path(r["template_path"]),
        status=CompanyStatus(r["status"]), notes=r["notes"],
    )


class InsuranceTemplateRepository:
    def __init__(self, db: Database) -> None:
        self._conn = db.connection

    def upsert(self, t: InsuranceTemplate) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO insurance_templates (id, name, internal_code, insurer,
                    firm, template_path, status, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, internal_code=excluded.internal_code,
                    insurer=excluded.insurer, firm=excluded.firm,
                    template_path=excluded.template_path,
                    status=excluded.status, notes=excluded.notes,
                    updated_at=excluded.updated_at
                """,
                (str(t.id), t.name, t.internal_code, t.insurer, t.firm,
                 str(t.template_path), t.status.value, t.notes, now, now),
            )

    def by_internal_code(self, code: str) -> InsuranceTemplate | None:
        row = self._conn.execute(
            "SELECT * FROM insurance_templates WHERE internal_code = ?", (code,)
        ).fetchone()
        return _row(row) if row else None

    def list_active(self) -> list[InsuranceTemplate]:
        rows = self._conn.execute(
            "SELECT * FROM insurance_templates WHERE status = ? ORDER BY name",
            (CompanyStatus.ACTIVE.value,),
        ).fetchall()
        return [_row(r) for r in rows]

    def archive(self, template_id: UUID) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                "UPDATE insurance_templates SET status=?, updated_at=? WHERE id=?",
                (CompanyStatus.ARCHIVED.value, now, str(template_id)),
            )

    def count(self) -> int:
        return int(self._conn.execute(
            "SELECT COUNT(*) AS n FROM insurance_templates").fetchone()["n"])
