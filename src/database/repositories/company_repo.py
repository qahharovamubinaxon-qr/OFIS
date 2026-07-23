"""Company persistence. The only code that touches the ``companies`` table."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from src.database.connection import Database
from src.domain.company import Company
from src.domain.enums import CompanyStatus, EmployerType


def _row_to_company(row: sqlite3.Row) -> Company:
    return Company(
        id=UUID(row["id"]),
        name=row["name"],
        internal_code=row["internal_code"],
        employer_type=EmployerType(row["employer_type"]),
        okved=row["okved"],
        ogrn=row["ogrn"],
        inn=row["inn"],
        address_index=row["address_index"],
        address_text=row["address_text"],
        phone=row["phone"],
        director_position=row["director_position"],
        director_fio=row["director_fio"],
        logo_path=Path(row["logo_path"]) if row["logo_path"] else None,
        template_path=Path(row["template_path"]),
        template_version=row["template_version"],
        status=CompanyStatus(row["status"]),
        notes=row["notes"],
    )


class CompanyRepository:
    def __init__(self, db: Database) -> None:
        self._conn = db.connection

    def upsert(self, c: Company) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO companies (id, name, internal_code, employer_type, okved, ogrn,
                    inn, address_index, address_text, phone, director_position, director_fio,
                    logo_path, template_path, template_version, status, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, internal_code=excluded.internal_code,
                    employer_type=excluded.employer_type, okved=excluded.okved,
                    ogrn=excluded.ogrn, inn=excluded.inn, address_index=excluded.address_index,
                    address_text=excluded.address_text, phone=excluded.phone,
                    director_position=excluded.director_position, director_fio=excluded.director_fio,
                    logo_path=excluded.logo_path, template_path=excluded.template_path,
                    template_version=excluded.template_version, status=excluded.status,
                    notes=excluded.notes, updated_at=excluded.updated_at
                """,
                (
                    str(c.id), c.name, c.internal_code, c.employer_type.value, c.okved, c.ogrn,
                    c.inn, c.address_index, c.address_text, c.phone, c.director_position,
                    c.director_fio, str(c.logo_path) if c.logo_path else None,
                    str(c.template_path), c.template_version, c.status.value, c.notes, now, now,
                ),
            )

    def get(self, company_id: UUID) -> Company | None:
        row = self._conn.execute("SELECT * FROM companies WHERE id = ?", (str(company_id),)).fetchone()
        return _row_to_company(row) if row else None

    def by_internal_code(self, code: str) -> Company | None:
        row = self._conn.execute(
            "SELECT * FROM companies WHERE internal_code = ?", (code,)
        ).fetchone()
        return _row_to_company(row) if row else None

    def list_active(self) -> list[Company]:
        rows = self._conn.execute(
            "SELECT * FROM companies WHERE status = ? ORDER BY name", (CompanyStatus.ACTIVE.value,)
        ).fetchall()
        return [_row_to_company(r) for r in rows]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) AS n FROM companies").fetchone()["n"])
