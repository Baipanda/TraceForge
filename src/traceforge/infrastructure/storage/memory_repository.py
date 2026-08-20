from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from traceforge.memory.models import (
    MemoryEntry,
    MemoryKind,
    MemoryScope,
    MemoryScopeRef,
    MemorySearchRequest,
)


class SqliteMemoryRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def upsert(self, entry: MemoryEntry) -> MemoryEntry:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO traceforge_memory_entries (
                    id, memory_key, workspace_id, kind, scope, scope_key, title, content,
                    source, source_event_id, source_request_id, source_message_id,
                    confidence, importance, tags_json, metadata_json,
                    created_at, updated_at, last_accessed_at, expires_at, deleted_at
                ) VALUES (
                    :id, :memory_key, :workspace_id, :kind, :scope, :scope_key, :title, :content,
                    :source, :source_event_id, :source_request_id, :source_message_id,
                    :confidence, :importance, :tags_json, :metadata_json,
                    :created_at, :updated_at, :last_accessed_at, :expires_at, :deleted_at
                )
                ON CONFLICT(memory_key) DO UPDATE SET
                    workspace_id = excluded.workspace_id,
                    kind = excluded.kind,
                    scope = excluded.scope,
                    scope_key = excluded.scope_key,
                    title = excluded.title,
                    content = excluded.content,
                    source = excluded.source,
                    source_event_id = excluded.source_event_id,
                    source_request_id = excluded.source_request_id,
                    source_message_id = excluded.source_message_id,
                    confidence = excluded.confidence,
                    importance = excluded.importance,
                    tags_json = excluded.tags_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    last_accessed_at = excluded.last_accessed_at,
                    expires_at = excluded.expires_at,
                    deleted_at = excluded.deleted_at
                """,
                _entry_params(entry),
            )
        return entry

    def search(self, request: MemorySearchRequest) -> list[MemoryEntry]:
        clauses = ["workspace_id = :workspace_id", "deleted_at IS NULL"]
        params: dict[str, Any] = {"workspace_id": request.workspace_id, "limit": request.limit}
        scope_clause = self._scope_clause(request.scope_refs, params)
        if scope_clause:
            clauses.append(scope_clause)
        text_clause = self._text_clause(request.text, params)
        if text_clause:
            clauses.append(text_clause)
        kind_clause = self._kind_clause(request.kinds, params)
        if kind_clause:
            clauses.append(kind_clause)
        sql = (
            "SELECT * FROM traceforge_memory_entries "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY importance DESC, last_accessed_at DESC, updated_at DESC "
            "LIMIT :limit"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            if rows:
                conn.executemany(
                    "UPDATE traceforge_memory_entries SET last_accessed_at = ? WHERE memory_key = ?",
                    [(_utcnow().isoformat(), row["memory_key"]) for row in rows],
                )
        return [_row_to_entry(row) for row in rows]

    def get(self, memory_key: str) -> MemoryEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM traceforge_memory_entries WHERE memory_key = ? AND deleted_at IS NULL",
                (memory_key,),
            ).fetchone()
        return _row_to_entry(row) if row else None

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS traceforge_memory_entries (
                    id TEXT PRIMARY KEY,
                    memory_key TEXT NOT NULL UNIQUE,
                    workspace_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_event_id TEXT,
                    source_request_id TEXT,
                    source_message_id TEXT,
                    confidence REAL NOT NULL DEFAULT 0.8,
                    importance INTEGER NOT NULL DEFAULT 0,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL,
                    expires_at TEXT,
                    deleted_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_traceforge_memory_workspace_scope
                ON traceforge_memory_entries (workspace_id, scope, scope_key);

                CREATE INDEX IF NOT EXISTS idx_traceforge_memory_workspace_kind
                ON traceforge_memory_entries (workspace_id, kind, importance);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _scope_clause(
        self,
        refs: tuple[MemoryScopeRef, ...],
        params: dict[str, Any],
    ) -> str | None:
        if not refs:
            return None
        parts: list[str] = []
        for index, ref in enumerate(refs):
            scope_name = f"scope_{index}"
            scope_key = f"scope_key_{index}"
            params[scope_name] = ref.scope.value
            params[scope_key] = ref.scope_key
            parts.append(f"(scope = :{scope_name} AND scope_key = :{scope_key})")
        return "(" + " OR ".join(parts) + ")"

    def _kind_clause(self, kinds: tuple[MemoryKind, ...], params: dict[str, Any]) -> str | None:
        if not kinds:
            return None
        names = []
        for index, kind in enumerate(kinds):
            key = f"kind_{index}"
            params[key] = kind.value
            names.append(f":{key}")
        return f"kind IN ({', '.join(names)})"

    def _text_clause(self, text: str, params: dict[str, Any]) -> str | None:
        tokens = _memory_tokens(text)
        if not tokens:
            return None
        parts: list[str] = []
        for index, token in enumerate(tokens[:6]):
            key = f"token_{index}"
            params[key] = f"%{token.lower()}%"
            parts.append(
                f"(lower(title) LIKE :{key} OR lower(content) LIKE :{key} OR lower(tags_json) LIKE :{key})"
            )
        return "(" + " OR ".join(parts) + ")"


def _entry_params(entry: MemoryEntry) -> dict[str, Any]:
    now = _utcnow().isoformat()
    return {
        "id": str(uuid4()),
        "memory_key": entry.memory_key,
        "workspace_id": entry.workspace_id,
        "kind": entry.kind.value,
        "scope": entry.scope.value,
        "scope_key": entry.scope_key,
        "title": entry.title,
        "content": entry.content,
        "source": entry.source,
        "source_event_id": entry.source_event_id,
        "source_request_id": entry.source_request_id,
        "source_message_id": entry.source_message_id,
        "confidence": entry.confidence,
        "importance": entry.importance,
        "tags_json": json.dumps(list(entry.tags), ensure_ascii=False),
        "metadata_json": json.dumps(entry.metadata, ensure_ascii=False, default=str),
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
        "last_accessed_at": entry.last_accessed_at.isoformat() if entry.last_accessed_at else now,
        "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
        "deleted_at": entry.deleted_at.isoformat() if entry.deleted_at else None,
    }


def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
    return MemoryEntry(
        memory_key=row["memory_key"],
        workspace_id=row["workspace_id"],
        kind=MemoryKind(row["kind"]),
        scope=MemoryScope(row["scope"]),
        scope_key=row["scope_key"],
        title=row["title"],
        content=row["content"],
        source=row["source"],
        source_event_id=row["source_event_id"],
        source_request_id=row["source_request_id"],
        source_message_id=row["source_message_id"],
        confidence=float(row["confidence"]),
        importance=int(row["importance"]),
        tags=tuple(json.loads(row["tags_json"] or "[]")),
        metadata=json.loads(row["metadata_json"] or "{}"),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        last_accessed_at=datetime.fromisoformat(row["last_accessed_at"]),
        expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
        deleted_at=datetime.fromisoformat(row["deleted_at"]) if row["deleted_at"] else None,
    )


def _memory_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current = []
    for char in text:
        if char.isalnum():
            current.append(char)
            continue
        if current:
            token = "".join(current).lower()
            if len(token) >= 2 and token not in tokens:
                tokens.append(token)
            current = []
    if current:
        token = "".join(current).lower()
        if len(token) >= 2 and token not in tokens:
            tokens.append(token)
    return tokens


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

