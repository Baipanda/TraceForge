from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from traceforge.core.events import WorkspaceEvent
from traceforge.core.todos import TodoAction, TodoFilter, TodoRecord, TodoStatus


class SqliteTodoRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create_todo(self, todo: TodoRecord, event: WorkspaceEvent | None = None) -> TodoRecord:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO traceforge_todos (
                    id, title, description, status, priority, workspace_id,
                    channel_name, topic, proposer_name, proposer_email,
                    assignee_name, assignee_email, source_message_id,
                    created_at, updated_at, completed_at, deleted_at
                ) VALUES (
                    :id, :title, :description, :status, :priority, :workspace_id,
                    :channel_name, :topic, :proposer_name, :proposer_email,
                    :assignee_name, :assignee_email, :source_message_id,
                    :created_at, :updated_at, :completed_at, :deleted_at
                )
                """,
                _todo_params(todo),
            )
            self._insert_todo_event(conn, todo.id, TodoAction.CREATE, event, {"todo": todo.to_dict()})
            self._upsert_session(conn, event)
        return todo

    def list_todos(self, todo_filter: TodoFilter) -> list[TodoRecord]:
        query = [
            "SELECT * FROM traceforge_todos",
            "WHERE workspace_id = :workspace_id",
            "AND deleted_at IS NULL",
        ]
        params: dict[str, Any] = {"workspace_id": todo_filter.workspace_id, "limit": todo_filter.limit}
        if todo_filter.status is not None:
            query.append("AND status = :status")
            params["status"] = todo_filter.status.value
        if todo_filter.assignee_email:
            query.append("AND assignee_email = :assignee_email")
            params["assignee_email"] = todo_filter.assignee_email
        if todo_filter.topic:
            query.append("AND topic = :topic")
            params["topic"] = todo_filter.topic
        query.append("ORDER BY created_at DESC LIMIT :limit")
        with self._connect() as conn:
            rows = conn.execute(" ".join(query), params).fetchall()
        return [_row_to_todo(row) for row in rows]

    def get_todo(self, todo_id: str) -> TodoRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM traceforge_todos WHERE id = ? AND deleted_at IS NULL",
                (todo_id,),
            ).fetchone()
        return _row_to_todo(row) if row else None

    def update_todo(
        self,
        todo_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TodoStatus | None = None,
        priority: int | None = None,
        assignee_name: str | None = None,
        assignee_email: str | None = None,
        event: WorkspaceEvent | None = None,
        extra: dict[str, Any] | None = None,
    ) -> TodoRecord:
        existing = self.get_todo(todo_id)
        if existing is None:
            raise KeyError(f"Todo not found: {todo_id}")
        updated = TodoRecord(
            id=existing.id,
            title=title if title is not None else existing.title,
            description=description if description is not None else existing.description,
            status=status if status is not None else existing.status,
            priority=priority if priority is not None else existing.priority,
            workspace_id=existing.workspace_id,
            channel_name=existing.channel_name,
            topic=existing.topic,
            proposer_name=existing.proposer_name,
            proposer_email=existing.proposer_email,
            assignee_name=assignee_name if assignee_name is not None else existing.assignee_name,
            assignee_email=assignee_email if assignee_email is not None else existing.assignee_email,
            source_message_id=existing.source_message_id,
            created_at=existing.created_at,
            updated_at=_utcnow(),
            completed_at=_utcnow() if status == TodoStatus.DONE else existing.completed_at,
            deleted_at=existing.deleted_at,
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE traceforge_todos
                SET title = :title,
                    description = :description,
                    status = :status,
                    priority = :priority,
                    assignee_name = :assignee_name,
                    assignee_email = :assignee_email,
                    updated_at = :updated_at,
                    completed_at = :completed_at
                WHERE id = :id
                """,
                _todo_params(updated),
            )
            detail = {"todo": updated.to_dict()}
            if extra:
                detail["extra"] = extra
            self._insert_todo_event(conn, updated.id, TodoAction.UPDATE, event, detail)
            self._upsert_session(conn, event)
        return updated

    def delete_todo(self, todo_id: str, *, event: WorkspaceEvent | None = None) -> TodoRecord:
        existing = self.get_todo(todo_id)
        if existing is None:
            raise KeyError(f"Todo not found: {todo_id}")
        deleted = TodoRecord(
            id=existing.id,
            title=existing.title,
            description=existing.description,
            status=TodoStatus.CANCELED,
            priority=existing.priority,
            workspace_id=existing.workspace_id,
            channel_name=existing.channel_name,
            topic=existing.topic,
            proposer_name=existing.proposer_name,
            proposer_email=existing.proposer_email,
            assignee_name=existing.assignee_name,
            assignee_email=existing.assignee_email,
            source_message_id=existing.source_message_id,
            created_at=existing.created_at,
            updated_at=_utcnow(),
            completed_at=existing.completed_at,
            deleted_at=_utcnow(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE traceforge_todos
                SET status = :status,
                    updated_at = :updated_at,
                    deleted_at = :deleted_at
                WHERE id = :id
                """,
                _todo_params(deleted),
            )
            self._insert_todo_event(conn, deleted.id, TodoAction.DELETE, event, {"todo": deleted.to_dict()})
            self._upsert_session(conn, event)
        return deleted

    def summarize_todos(self, todo_filter: TodoFilter) -> dict[str, Any]:
        todos = self.list_todos(todo_filter)
        summary: dict[str, int] = {}
        for item in todos:
            summary[item.status.value] = summary.get(item.status.value, 0) + 1
        return {
            "workspace_id": todo_filter.workspace_id,
            "total": len(todos),
            "by_status": summary,
            "todos": [todo.to_dict() for todo in todos],
        }

    def record_session(self, event: WorkspaceEvent, session_key: str) -> None:
        with self._connect() as conn:
            self._upsert_session(conn, event, session_key=session_key)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS traceforge_todos (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    workspace_id TEXT NOT NULL,
                    channel_name TEXT,
                    topic TEXT,
                    proposer_name TEXT,
                    proposer_email TEXT,
                    assignee_name TEXT,
                    assignee_email TEXT,
                    source_message_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    deleted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS traceforge_todo_events (
                    id TEXT PRIMARY KEY,
                    todo_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_name TEXT,
                    actor_email TEXT,
                    detail_json TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS traceforge_sessions (
                    session_key TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    channel_name TEXT,
                    topic TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _insert_todo_event(
        self,
        conn: sqlite3.Connection,
        todo_id: str,
        action: TodoAction,
        event: WorkspaceEvent | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        payload = json.dumps(detail or {}, ensure_ascii=False)
        conn.execute(
            """
            INSERT INTO traceforge_todo_events (
                id, todo_id, action, actor_name, actor_email, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                todo_id,
                action.value,
                event.actor.display_name if event else None,
                event.actor.email if event else None,
                payload,
                _utcnow().isoformat(),
            ),
        )

    def _upsert_session(
        self,
        conn: sqlite3.Connection,
        event: WorkspaceEvent | None,
        *,
        session_key: str | None = None,
    ) -> None:
        if event is None:
            return
        now = _utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO traceforge_sessions (
                session_key, workspace_id, channel_name, topic, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_key) DO UPDATE SET
                workspace_id = excluded.workspace_id,
                channel_name = excluded.channel_name,
                topic = excluded.topic,
                updated_at = excluded.updated_at
            """,
            (
                session_key or event.route_key(),
                event.location.workspace_id,
                event.location.channel_name,
                event.location.topic,
                now,
                now,
            ),
        )


def _todo_params(todo: TodoRecord) -> dict[str, Any]:
    return {
        "id": todo.id,
        "title": todo.title,
        "description": todo.description,
        "status": todo.status.value,
        "priority": todo.priority,
        "workspace_id": todo.workspace_id,
        "channel_name": todo.channel_name,
        "topic": todo.topic,
        "proposer_name": todo.proposer_name,
        "proposer_email": todo.proposer_email,
        "assignee_name": todo.assignee_name,
        "assignee_email": todo.assignee_email,
        "source_message_id": todo.source_message_id,
        "created_at": todo.created_at.isoformat(),
        "updated_at": todo.updated_at.isoformat(),
        "completed_at": todo.completed_at.isoformat() if todo.completed_at else None,
        "deleted_at": todo.deleted_at.isoformat() if todo.deleted_at else None,
    }


def _row_to_todo(row: sqlite3.Row) -> TodoRecord:
    return TodoRecord(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        status=TodoStatus(row["status"]),
        priority=int(row["priority"]),
        workspace_id=row["workspace_id"],
        channel_name=row["channel_name"],
        topic=row["topic"],
        proposer_name=row["proposer_name"],
        proposer_email=row["proposer_email"],
        assignee_name=row["assignee_name"],
        assignee_email=row["assignee_email"],
        source_message_id=row["source_message_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        deleted_at=datetime.fromisoformat(row["deleted_at"]) if row["deleted_at"] else None,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
