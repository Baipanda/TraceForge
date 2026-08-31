"""Workspace Person store (SQLite): TraceForge identity + external bindings."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from traceforge.config import get_settings

PROVIDER_ZULIP = "zulip"

# Bootstrap demo identities so assignee-by-name works before first message.
_DEMO_SEEDS: tuple[dict[str, str], ...] = (
    {
        "display_name": "Admin",
        "primary_email": "traceforge-admin@example.local",
        "external_id": "8",
        "binding_email": "traceforge-admin@example.local",
    },
    {
        "display_name": "Neymar",
        "primary_email": "neymar@traceforge.local",
        "external_id": "9",
        "binding_email": "neymar@traceforge.local",
    },
    {
        "display_name": "Peter",
        "primary_email": "peter@traceforge.local",
        "external_id": "11",
        "binding_email": "peter@traceforge.local",
    },
    {
        "display_name": "Gwen",
        "primary_email": "gwen@traceforge.local",
        "external_id": "12",
        "binding_email": "gwen@traceforge.local",
    },
)


@dataclass(frozen=True)
class PersonRecord:
    person_id: str
    display_name: str | None
    primary_email: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "person_id": self.person_id,
            "display_name": self.display_name,
            "primary_email": self.primary_email,
            # Compatibility aliases for todo / tools that previously used IdentityRecord.
            "canonical_name": self.display_name,
            "email": self.primary_email,
        }


class PersonStore:
    """persons + person_bindings in the TraceForge SQLite database."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = get_settings().traceforge_db_path
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def resolve_or_create(
        self,
        *,
        provider: str,
        external_id: str,
        email: str | None = None,
        display_name: str | None = None,
    ) -> PersonRecord:
        provider = (provider or "").strip().casefold()
        external_id = (external_id or "").strip()
        email = (email or "").strip() or None
        display_name = (display_name or "").strip() or None
        if not provider or not external_id:
            raise ValueError("provider and external_id are required")

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT p.person_id, p.display_name, p.primary_email
                FROM person_bindings b
                JOIN persons p ON p.person_id = b.person_id
                WHERE b.provider = ? AND b.external_id = ?
                """,
                (provider, external_id),
            ).fetchone()
            if row:
                person = _row_to_person(row)
                self._touch_binding(conn, provider, external_id, email, display_name, person)
                return person

            if email:
                row = conn.execute(
                    """
                    SELECT person_id, display_name, primary_email
                    FROM persons
                    WHERE lower(primary_email) = lower(?)
                    """,
                    (email,),
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        """
                        SELECT p.person_id, p.display_name, p.primary_email
                        FROM person_bindings b
                        JOIN persons p ON p.person_id = b.person_id
                        WHERE b.email IS NOT NULL AND lower(b.email) = lower(?)
                        LIMIT 1
                        """,
                        (email,),
                    ).fetchone()
                if row:
                    person = _row_to_person(row)
                    self._upsert_binding(conn, person.person_id, provider, external_id, email)
                    self._maybe_update_person(conn, person.person_id, display_name, email)
                    return self.get(person.person_id) or person

            person_id = str(uuid4())
            now = _utcnow()
            conn.execute(
                """
                INSERT INTO persons (person_id, display_name, primary_email, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (person_id, display_name, email, now, now),
            )
            self._upsert_binding(conn, person_id, provider, external_id, email)
            return PersonRecord(person_id=person_id, display_name=display_name, primary_email=email)

    def resolve(self, query: str | None) -> PersonRecord | None:
        if not query:
            return None
        needle = query.strip()
        if not needle:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT person_id, display_name, primary_email FROM persons
                WHERE person_id = ?
                """,
                (needle,),
            ).fetchone()
            if row:
                return _row_to_person(row)
            row = conn.execute(
                """
                SELECT person_id, display_name, primary_email FROM persons
                WHERE primary_email IS NOT NULL AND lower(primary_email) = lower(?)
                """,
                (needle,),
            ).fetchone()
            if row:
                return _row_to_person(row)
            row = conn.execute(
                """
                SELECT person_id, display_name, primary_email FROM persons
                WHERE display_name IS NOT NULL AND lower(display_name) = lower(?)
                """,
                (needle,),
            ).fetchone()
            if row:
                return _row_to_person(row)
            row = conn.execute(
                """
                SELECT p.person_id, p.display_name, p.primary_email
                FROM person_bindings b
                JOIN persons p ON p.person_id = b.person_id
                WHERE b.external_id = ?
                   OR (b.email IS NOT NULL AND lower(b.email) = lower(?))
                LIMIT 1
                """,
                (needle, needle),
            ).fetchone()
            if row:
                return _row_to_person(row)
        return None

    def get(self, person_id: str) -> PersonRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT person_id, display_name, primary_email FROM persons
                WHERE person_id = ?
                """,
                (person_id,),
            ).fetchone()
        return _row_to_person(row) if row else None

    def list(self) -> list[PersonRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT person_id, display_name, primary_email FROM persons
                ORDER BY display_name COLLATE NOCASE, person_id
                """
            ).fetchall()
        return [_row_to_person(row) for row in rows]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS persons (
                    person_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    primary_email TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_persons_primary_email
                    ON persons (primary_email)
                    WHERE primary_email IS NOT NULL;

                CREATE TABLE IF NOT EXISTS person_bindings (
                    provider TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    person_id TEXT NOT NULL,
                    email TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, external_id),
                    FOREIGN KEY (person_id) REFERENCES persons(person_id)
                );

                CREATE INDEX IF NOT EXISTS idx_person_bindings_person
                    ON person_bindings (person_id);
                CREATE INDEX IF NOT EXISTS idx_person_bindings_email
                    ON person_bindings (email);
                """
            )
            count = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
            if count == 0:
                self._seed_demo_persons(conn)

    def _seed_demo_persons(self, conn: sqlite3.Connection) -> None:
        now = _utcnow()
        for seed in _DEMO_SEEDS:
            person_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO persons (person_id, display_name, primary_email, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (person_id, seed["display_name"], seed["primary_email"], now, now),
            )
            conn.execute(
                """
                INSERT INTO person_bindings (
                    provider, external_id, person_id, email, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    PROVIDER_ZULIP,
                    seed["external_id"],
                    person_id,
                    seed["binding_email"],
                    now,
                    now,
                ),
            )

    def _upsert_binding(
        self,
        conn: sqlite3.Connection,
        person_id: str,
        provider: str,
        external_id: str,
        email: str | None,
    ) -> None:
        now = _utcnow()
        conn.execute(
            """
            INSERT INTO person_bindings (
                provider, external_id, person_id, email, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, external_id) DO UPDATE SET
                person_id = excluded.person_id,
                email = COALESCE(excluded.email, person_bindings.email),
                updated_at = excluded.updated_at
            """,
            (provider, external_id, person_id, email, now, now),
        )

    def _touch_binding(
        self,
        conn: sqlite3.Connection,
        provider: str,
        external_id: str,
        email: str | None,
        display_name: str | None,
        person: PersonRecord,
    ) -> None:
        now = _utcnow()
        if email:
            conn.execute(
                """
                UPDATE person_bindings
                SET email = ?, updated_at = ?
                WHERE provider = ? AND external_id = ?
                """,
                (email, now, provider, external_id),
            )
        self._maybe_update_person(conn, person.person_id, display_name, email)

    def _maybe_update_person(
        self,
        conn: sqlite3.Connection,
        person_id: str,
        display_name: str | None,
        email: str | None,
    ) -> None:
        now = _utcnow()
        if display_name:
            conn.execute(
                """
                UPDATE persons SET display_name = ?, updated_at = ?
                WHERE person_id = ? AND (display_name IS NULL OR display_name = '')
                """,
                (display_name, now, person_id),
            )
        if email:
            conn.execute(
                """
                UPDATE persons SET primary_email = ?, updated_at = ?
                WHERE person_id = ? AND (primary_email IS NULL OR primary_email = '')
                """,
                (email, now, person_id),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def _row_to_person(row: sqlite3.Row | tuple[Any, ...]) -> PersonRecord:
    if isinstance(row, sqlite3.Row):
        return PersonRecord(
            person_id=str(row["person_id"]),
            display_name=row["display_name"],
            primary_email=row["primary_email"],
        )
    return PersonRecord(
        person_id=str(row[0]),
        display_name=row[1],
        primary_email=row[2],
    )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
