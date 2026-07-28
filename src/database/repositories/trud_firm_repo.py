"""TrudFirm persistence. The only code touching the ``trud_firms`` table."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from src.database.connection import Database
from src.domain.enums import CompanyStatus, LegalForm
from src.domain.firm_details import FirmDetails
from src.domain.trud_firm import TrudFirm

#: The requisites of a hand-typed firm. An uploaded firm leaves them NULL,
#: which is how the two kinds are told apart on read.
_DETAIL_COLUMNS = ("legal_form", "short_name", "inn", "kpp", "ogrn", "okved",
                   "address", "district", "mvd_office", "director",
                   "director_position", "phone", "stamp_path")


def _get(r: sqlite3.Row, column: str):
    return r[column] if column in r.keys() else None


def _details(r: sqlite3.Row) -> FirmDetails | None:
    if not _get(r, "legal_form"):
        return None
    stamp = _get(r, "stamp_path")
    return FirmDetails(
        legal_form=LegalForm(r["legal_form"]), name=r["name"],
        short_name=_get(r, "short_name") or "", inn=_get(r, "inn") or "",
        kpp=_get(r, "kpp") or "", ogrn=_get(r, "ogrn") or "",
        okved=_get(r, "okved") or "", address=_get(r, "address") or "",
        district=_get(r, "district") or "",
        mvd_office=_get(r, "mvd_office") or "",
        director=_get(r, "director") or "",
        director_position=_get(r, "director_position") or "Генеральный директор",
        phone=_get(r, "phone") or "",
        stamp_path=Path(stamp) if stamp else None,
    )


def _row(r: sqlite3.Row) -> TrudFirm:
    return TrudFirm(
        id=UUID(r["id"]), name=r["name"], internal_code=r["internal_code"],
        trud_template_path=Path(r["trud_template_path"]),
        uved_template_path=Path(r["uved_template_path"]),
        hod_template_path=(Path(r["hod_template_path"])
                           if _get(r, "hod_template_path") else None),
        details=_details(r),
        status=CompanyStatus(r["status"]), notes=r["notes"],
    )


def _detail_values(d: FirmDetails | None) -> tuple:
    if d is None:
        return (None,) * len(_DETAIL_COLUMNS)
    return (d.legal_form.value, d.short_name, d.inn, d.kpp, d.ogrn, d.okved,
            d.address, d.district, d.mvd_office, d.director,
            d.director_position, d.phone,
            str(d.stamp_path) if d.stamp_path else None)


class TrudFirmRepository:
    def __init__(self, db: Database) -> None:
        self._conn = db.connection

    def upsert(self, f: TrudFirm) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        details = ", ".join(_DETAIL_COLUMNS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in _DETAIL_COLUMNS)
        placeholders = ",".join("?" * len(_DETAIL_COLUMNS))
        with self._conn:
            self._conn.execute(
                f"""
                INSERT INTO trud_firms (id, name, internal_code, trud_template_path,
                    uved_template_path, hod_template_path, status, notes,
                    created_at, updated_at, {details})
                VALUES (?,?,?,?,?,?,?,?,?,?,{placeholders})
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, internal_code=excluded.internal_code,
                    trud_template_path=excluded.trud_template_path,
                    uved_template_path=excluded.uved_template_path,
                    hod_template_path=excluded.hod_template_path,
                    status=excluded.status, notes=excluded.notes,
                    updated_at=excluded.updated_at, {updates}
                """,
                (str(f.id), f.name, f.internal_code, str(f.trud_template_path),
                 str(f.uved_template_path),
                 str(f.hod_template_path) if f.hod_template_path else None,
                 f.status.value, f.notes, now, now) + _detail_values(f.details),
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
