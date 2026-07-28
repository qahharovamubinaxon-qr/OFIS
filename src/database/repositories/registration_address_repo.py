"""Registration-address persistence. The only code touching that table."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from src.database.connection import Database
from src.domain.enums import CompanyStatus
from src.domain.registration_address import RegistrationAddress

_ADDR_COLS = ("oblast", "raion", "gorod", "ulitsa", "dom", "korpus",
              "stroenie", "kvartira", "regional_number",
              "kind", "organization_name", "inn", "komnata",
              "stay_from_x", "stay_from_y")


def _row_to_address(row: sqlite3.Row) -> RegistrationAddress:
    keys = row.keys()
    extra = {c: row[c] for c in _ADDR_COLS if c in keys}
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
        **extra,
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
                    host_fio, oblast, raion, gorod, ulitsa, dom, korpus, stroenie, kvartira,
                    regional_number, kind, organization_name, inn, komnata,
                    stay_from_x, stay_from_y,
                    template_path, template_version, status, notes,
                    created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    label=excluded.label, internal_code=excluded.internal_code,
                    address_text=excluded.address_text, host_fio=excluded.host_fio,
                    oblast=excluded.oblast, raion=excluded.raion, gorod=excluded.gorod,
                    ulitsa=excluded.ulitsa, dom=excluded.dom, korpus=excluded.korpus,
                    stroenie=excluded.stroenie, kvartira=excluded.kvartira,
                    regional_number=excluded.regional_number,
                    kind=excluded.kind, organization_name=excluded.organization_name,
                    inn=excluded.inn, komnata=excluded.komnata,
                    stay_from_x=excluded.stay_from_x, stay_from_y=excluded.stay_from_y,
                    template_path=excluded.template_path, template_version=excluded.template_version,
                    status=excluded.status, notes=excluded.notes, updated_at=excluded.updated_at
                """,
                (
                    str(a.id), a.label, a.internal_code, a.address_text, a.host_fio,
                    a.oblast, a.raion, a.gorod, a.ulitsa, a.dom, a.korpus, a.stroenie,
                    a.kvartira, a.regional_number,
                    a.kind, a.organization_name, a.inn, a.komnata,
                    a.stay_from_x, a.stay_from_y,
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

    def list_active(self, kind: str | None = None) -> list[RegistrationAddress]:
        if kind is None:
            rows = self._conn.execute(
                "SELECT * FROM registration_addresses WHERE status = ? ORDER BY label",
                (CompanyStatus.ACTIVE.value,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM registration_addresses WHERE status = ? AND kind = ? "
                "ORDER BY label",
                (CompanyStatus.ACTIVE.value, kind),
            ).fetchall()
        return [_row_to_address(r) for r in rows]

    def list_archived(self, kind: str | None = None) -> list[RegistrationAddress]:
        """Removed addresses are only hidden, never deleted — so an accidental
        click can be undone."""
        if kind is None:
            rows = self._conn.execute(
                "SELECT * FROM registration_addresses WHERE status != ? ORDER BY label",
                (CompanyStatus.ACTIVE.value,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM registration_addresses WHERE status != ? AND kind = ? "
                "ORDER BY label",
                (CompanyStatus.ACTIVE.value, kind),
            ).fetchall()
        return [_row_to_address(r) for r in rows]

    def restore(self, address_id: UUID) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                "UPDATE registration_addresses SET status=?, updated_at=? WHERE id=?",
                (CompanyStatus.ACTIVE.value, now, str(address_id)),
            )

    def archive(self, address_id: UUID) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                "UPDATE registration_addresses SET status=?, updated_at=? WHERE id=?",
                (CompanyStatus.ARCHIVED.value, now, str(address_id)),
            )

    def count(self) -> int:
        return int(
            self._conn.execute("SELECT COUNT(*) AS n FROM registration_addresses").fetchone()["n"]
        )
