"""Registration-address persistence. The only code touching that table."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from src.database.connection import Database
from src.domain.enums import CompanyStatus
from src.domain.registration_address import RegistrationAddress


def _row_to_address(row: sqlite3.Row) -> RegistrationAddress:
    return RegistrationAddress(
        id=UUID(row["id"]),
        label=row["label"],
        internal_code=row["internal_code"],
        address_text=row["address_text"],
        host_fio=row["host_fio"],
        template_path=Path(row["template_path"]),
        template_version=row["template_version"],
        status=CompanyStatus(row["status"]),
        notes=row["notes"],
    )


class RegistrationAddressRepository:
    def __init__(self, db: Database) -> None:
        self._conn = db.connection

    def upsert(self, a: RegistrationAddress) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO registration_addresses (id, label, internal_code, address_text,
                    host_fio, template_path, template_version, status, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    label=excluded.label, internal_code=excluded.internal_code,
                    address_text=excluded.address_text, host_fio=excluded.host_fio,
                    template_path=excluded.template_path, template_version=excluded.template_version,
                    status=excluded.status, notes=excluded.notes, updated_at=excluded.updated_at
                """,
                (
                    str(a.id), a.label, a.internal_code, a.address_text, a.host_fio,
                    str(a.template_path), a.template_version, a.status.value, a.notes, now, now,
                ),
            )

    def get(self, address_id: UUID) -> RegistrationAddress | None:
        row = self._conn.execute(
            "SELECT * FROM registration_addresses WHERE id = ?", (str(address_id),)
        ).fetchone()
        return _row_to_address(row) if row else None

    def by_internal_code(self, code: str) -> RegistrationAddress | None:
        row = self._conn.execute(
            "SELECT * FROM registration_addresses WHERE internal_code = ?", (code,)
        ).fetchone()
        return _row_to_address(row) if row else None

    def list_active(self) -> list[RegistrationAddress]:
        rows = self._conn.execute(
            "SELECT * FROM registration_addresses WHERE status = ? ORDER BY label",
            (CompanyStatus.ACTIVE.value,),
        ).fetchall()
        return [_row_to_address(r) for r in rows]

    def count(self) -> int:
        return int(
            self._conn.execute("SELECT COUNT(*) AS n FROM registration_addresses").fetchone()["n"]
        )
