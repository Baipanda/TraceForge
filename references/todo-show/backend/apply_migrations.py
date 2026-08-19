"""Apply SQL migrations from the project migrations directory."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"


def main() -> None:
    load_dotenv(ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("No migrations found.")
        return

    with psycopg2.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                       version TEXT PRIMARY KEY,
                       applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                   )"""
            )
            for path in files:
                version = path.name
                cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
                if cur.fetchone():
                    print(f"Migration already applied: {version}")
                    continue
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
                print(f"Applied migration: {version}")
        conn.commit()


if __name__ == "__main__":
    main()
