"""Apply SQL migrations under ../migrations."""
from __future__ import annotations

import sys
from pathlib import Path

from database import DATABASE_PATH, get_conn

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def main() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            row[0]
            for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
        }
        files = sorted(p for p in MIGRATIONS.glob("*.sql"))
        if not files:
            print("No migration files found", file=sys.stderr)
            sys.exit(1)
        for path in files:
            if path.name in applied:
                print(f"skip {path.name}")
                continue
            sql = path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations(filename, applied_at) VALUES (?, datetime('now'))",
                (path.name,),
            )
            conn.commit()
            print(f"apply {path.name}")
    print(f"database ready: {DATABASE_PATH}")


if __name__ == "__main__":
    main()
