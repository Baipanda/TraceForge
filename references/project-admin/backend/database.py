"""SQLite helpers for project-admin."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DB = _ROOT / "data" / "project_admin.sqlite3"
DATABASE_PATH = Path(os.getenv("PROJECT_ADMIN_DB", str(_DEFAULT_DB))).expanduser()


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple | list = ()) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def query_one(sql: str, params: tuple | list = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list = ()) -> None:
    with get_conn() as conn:
        conn.execute(sql, params)
        conn.commit()


def execute_returning_id(sql: str, params: tuple | list = ()) -> int:
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return int(cur.lastrowid)
