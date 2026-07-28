"""Studied-template persistence. The only code touching that table."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from src.database.connection import Database
from src.services.template_study import Study


def file_hash(path: Path) -> str:
    """What identifies a template: its contents, not its name or its folder."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class TemplateProfileRepository:
    def __init__(self, db: Database) -> None:
        self._conn = db.connection

    def save(self, name: str, path: Path, study: Study) -> UUID:
        now = datetime.now().isoformat(timespec="seconds")
        digest = file_hash(path)
        existing = self._row(digest)
        profile_id = UUID(existing["id"]) if existing else uuid4()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO template_profiles (id, name, file_hash, template_path,
                    kind, map_json, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(file_hash) DO UPDATE SET
                    name=excluded.name, template_path=excluded.template_path,
                    kind=excluded.kind, map_json=excluded.map_json,
                    updated_at=excluded.updated_at
                """,
                (str(profile_id), name, digest, str(path), study.kind,
                 json.dumps(study.to_json(), ensure_ascii=False), now, now),
            )
        return profile_id

    def for_file(self, path: Path) -> Study | None:
        """The confirmed map for this exact file, if it was studied before."""
        row = self._row(file_hash(path))
        return Study.from_json(json.loads(row["map_json"])) if row else None

    def list(self) -> list[tuple[str, str, Path]]:
        rows = self._conn.execute(
            "SELECT name, kind, template_path FROM template_profiles ORDER BY name"
        ).fetchall()
        return [(r["name"], r["kind"], Path(r["template_path"])) for r in rows]

    def forget(self, path: Path) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM template_profiles WHERE file_hash = ?",
                               (file_hash(path),))

    def _row(self, digest: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM template_profiles WHERE file_hash = ?", (digest,)
        ).fetchone()
