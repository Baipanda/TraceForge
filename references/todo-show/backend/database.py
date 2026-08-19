"""Database connection pool and query helpers."""
import os
import uuid
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool
from dotenv import load_dotenv

# Let psycopg2 handle Python uuid.UUID ↔ PostgreSQL uuid automatically
psycopg2.extras.register_uuid()

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")

# Thread-safe connection pool
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=DATABASE_URL,
        )
    return _pool


@contextmanager
def get_conn():
    """Yield a connection from the pool (context manager)."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


@contextmanager
def transaction():
    """Yield a connection inside a commit/rollback transaction."""
    with get_conn() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT query and return rows as list of dicts."""
    with get_conn() as conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        except Exception:
            conn.rollback()
            raise


def query_one(sql: str, params: tuple = ()) -> Optional[dict]:
    """Run a SELECT query and return a single row (or None)."""
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple = ()) -> None:
    """Run an INSERT/UPDATE/DELETE and commit."""
    with get_conn() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
