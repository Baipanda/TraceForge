from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from traceforge.core.events import WorkspaceEvent
from traceforge.core.subtrees import (
    DEFAULT_SUBTREE_FALLBACK_CODE,
    TOPIC_DEFAULT_SUBTREE_CODE,
    SubtreeRecord,
)
from traceforge.core.todos import TodoAction, TodoFilter, TodoRecord, TodoStatus
from traceforge.infrastructure.storage.subtree_defaults import DEFAULT_SUBTREE_SEEDS

_TODO_COLUMNS = (
    "id",
    "title",
    "status",
    "priority",
    "workspace_id",
    "subtree_id",
    "channel_name",
    "topic",
    "proposer_name",
    "proposer_email",
    "assignee_name",
    "assignee_email",
    "source_message_id",
    "created_at",
    "updated_at",
    "completed_at",
    "deleted_at",
)


class SqliteTodoRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def create_todo(self, todo: TodoRecord, event: WorkspaceEvent | None = None) -> TodoRecord:
        if not todo.subtree_id:
            raise ValueError("subtree_id is required")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO traceforge_todos (
                    id, title, description, status, priority, workspace_id, subtree_id,
                    channel_name, topic, proposer_name, proposer_email,
                    assignee_name, assignee_email, source_message_id,
                    created_at, updated_at, completed_at, deleted_at
                ) VALUES (
                    :id, :title, :description, :status, :priority, :workspace_id, :subtree_id,
                    :channel_name, :topic, :proposer_name, :proposer_email,
                    :assignee_name, :assignee_email, :source_message_id,
                    :created_at, :updated_at, :completed_at, :deleted_at
                )
                """,
                _todo_params(todo),
            )
            self._insert_todo_event(conn, todo.id, TodoAction.CREATE, event, {"todo": todo.to_dict()})
            self._upsert_session(conn, event)
        return self._attach_subtree_label(todo)

    def list_todos(self, todo_filter: TodoFilter) -> list[TodoRecord]:
        columns = list(_TODO_COLUMNS)
        if todo_filter.include_description:
            columns.insert(2, "description")
        query = [
            f"SELECT {', '.join(columns)} FROM traceforge_todos",
            "WHERE deleted_at IS NULL",
        ]
        params: dict[str, Any] = {"limit": todo_filter.limit}
        if todo_filter.workspace_id:
            query.append("AND workspace_id = :workspace_id")
            params["workspace_id"] = todo_filter.workspace_id
        if todo_filter.status is not None:
            query.append("AND status = :status")
            params["status"] = todo_filter.status.value
        if todo_filter.assignee_email:
            query.append("AND assignee_email = :assignee_email")
            params["assignee_email"] = todo_filter.assignee_email
        if todo_filter.assignee_name:
            query.append("AND assignee_name = :assignee_name")
            params["assignee_name"] = todo_filter.assignee_name
        if todo_filter.proposer_email:
            query.append("AND proposer_email = :proposer_email")
            params["proposer_email"] = todo_filter.proposer_email
        if todo_filter.proposer_name:
            query.append("AND proposer_name = :proposer_name")
            params["proposer_name"] = todo_filter.proposer_name
        if todo_filter.topic:
            query.append("AND topic = :topic")
            params["topic"] = todo_filter.topic
        if todo_filter.channel_name:
            query.append("AND channel_name = :channel_name")
            params["channel_name"] = todo_filter.channel_name
        if todo_filter.priority is not None:
            query.append("AND priority = :priority")
            params["priority"] = todo_filter.priority
        if todo_filter.title_contains:
            query.append("AND title LIKE :title_contains")
            params["title_contains"] = f"%{todo_filter.title_contains}%"
        if todo_filter.subtree_id and not todo_filter.include_descendants:
            query.append("AND subtree_id = :subtree_id")
            params["subtree_id"] = todo_filter.subtree_id
        elif todo_filter.subtree_path_prefix:
            query.append(
                "AND subtree_id IN ("
                "SELECT id FROM org_subtrees "
                "WHERE workspace_id = :subtree_workspace_id AND deleted_at IS NULL "
                "AND (path = :subtree_path_prefix OR path LIKE :subtree_path_like)"
                ")"
            )
            params["subtree_workspace_id"] = todo_filter.workspace_id or "default"
            prefix = todo_filter.subtree_path_prefix
            params["subtree_path_prefix"] = prefix
            params["subtree_path_like"] = prefix + "%"
        elif todo_filter.subtree_id and todo_filter.include_descendants:
            query.append(
                "AND subtree_id IN ("
                "SELECT c.id FROM org_subtrees c "
                "JOIN org_subtrees root ON root.workspace_id = c.workspace_id "
                "WHERE root.id = :subtree_id AND c.deleted_at IS NULL "
                "AND root.deleted_at IS NULL "
                "AND (c.id = root.id OR c.path LIKE root.path || '%')"
                ")"
            )
            params["subtree_id"] = todo_filter.subtree_id
        query.append("ORDER BY created_at DESC LIMIT :limit")
        with self._connect() as conn:
            rows = conn.execute(" ".join(query), params).fetchall()
            labels = self._subtree_label_map(conn)
        return [
            _row_to_todo(row, include_description=todo_filter.include_description, labels=labels)
            for row in rows
        ]

    def get_todo(self, todo_id: str) -> TodoRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM traceforge_todos WHERE id = ? AND deleted_at IS NULL",
                (todo_id,),
            ).fetchone()
            if row is None:
                return None
            labels = self._subtree_label_map(conn)
        return _row_to_todo(row, include_description=True, labels=labels)

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
        subtree_id: str | None = None,
        event: WorkspaceEvent | None = None,
        extra: dict[str, Any] | None = None,
        at: datetime | None = None,
        completed_at: datetime | None = None,
        completed_at_provided: bool = False,
    ) -> TodoRecord:
        existing = self.get_todo(todo_id)
        if existing is None:
            raise KeyError(f"Todo not found: {todo_id}")
        stamp = at or _utcnow()
        next_status = status if status is not None else existing.status
        next_subtree = subtree_id if subtree_id is not None else existing.subtree_id
        if not next_subtree:
            raise ValueError("subtree_id is required")
        updated = TodoRecord(
            id=existing.id,
            title=title if title is not None else existing.title,
            description=description if description is not None else existing.description,
            status=next_status,
            priority=priority if priority is not None else existing.priority,
            workspace_id=existing.workspace_id,
            subtree_id=next_subtree,
            channel_name=existing.channel_name,
            topic=existing.topic,
            proposer_name=existing.proposer_name,
            proposer_email=existing.proposer_email,
            assignee_name=assignee_name if assignee_name is not None else existing.assignee_name,
            assignee_email=assignee_email if assignee_email is not None else existing.assignee_email,
            source_message_id=existing.source_message_id,
            created_at=existing.created_at,
            updated_at=stamp,
            completed_at=_resolve_completed_at(
                existing=existing,
                next_status=next_status,
                status_provided=status is not None,
                at=stamp,
                explicit_completed_at=completed_at,
                explicit_completed_at_provided=completed_at_provided,
            ),
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
                    subtree_id = :subtree_id,
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
            labels = self._subtree_label_map(conn)
        return self._attach_subtree_label(updated, labels)

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
            subtree_id=existing.subtree_id,
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
            subtree_label=existing.subtree_label,
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

    def ensure_subtrees_for_workspace(self, workspace_id: str) -> None:
        with self._connect() as conn:
            self._seed_default_subtrees(conn, workspace_id)

    def get_subtree(self, subtree_id: str) -> SubtreeRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM org_subtrees WHERE id = ? AND deleted_at IS NULL",
                (subtree_id,),
            ).fetchone()
        return _row_to_subtree(row) if row else None

    def ancestor_chain(self, workspace_id: str, subtree_id: str) -> list[SubtreeRecord]:
        """Walk parent_id from node up to L1 (node first, then parents)."""
        chain: list[SubtreeRecord] = []
        current = self.find_subtree(workspace_id, subtree_id=subtree_id)
        seen: set[str] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            chain.append(current)
            if not current.parent_id:
                break
            current = self.find_subtree(workspace_id, subtree_id=current.parent_id)
        return chain

    def path_label_from_ancestors(self, workspace_id: str, subtree_id: str) -> str:
        chain = self.ancestor_chain(workspace_id, subtree_id)
        names = [node.name for node in reversed(chain)]
        return " / ".join(names) if names else subtree_id

    def find_subtree(

        self,
        workspace_id: str,
        *,
        subtree_id: str | None = None,
        code: str | None = None,
        name: str | None = None,
    ) -> SubtreeRecord | None:
        with self._connect() as conn:
            self._seed_default_subtrees(conn, workspace_id)
            if subtree_id:
                row = conn.execute(
                    """
                    SELECT * FROM org_subtrees
                    WHERE workspace_id = ? AND id = ? AND deleted_at IS NULL
                    """,
                    (workspace_id, subtree_id),
                ).fetchone()
                if row:
                    return _row_to_subtree(row)
            if code:
                row = conn.execute(
                    """
                    SELECT * FROM org_subtrees
                    WHERE workspace_id = ? AND code = ? AND deleted_at IS NULL
                    """,
                    (workspace_id, code.strip()),
                ).fetchone()
                if row:
                    return _row_to_subtree(row)
            if name:
                # Prefer deepest match (L3 over L2/L1) so a leaf name alone resolves
                # and parents can be filled via parent_id.
                row = conn.execute(
                    """
                    SELECT * FROM org_subtrees
                    WHERE workspace_id = ? AND name = ? AND deleted_at IS NULL
                    ORDER BY level DESC, sort_order ASC
                    LIMIT 1
                    """,
                    (workspace_id, name.strip()),
                ).fetchone()
                if row:
                    return _row_to_subtree(row)
                row = conn.execute(
                    """
                    SELECT * FROM org_subtrees
                    WHERE workspace_id = ? AND deleted_at IS NULL
                      AND (name LIKE ? OR code LIKE ?)
                    ORDER BY level DESC, sort_order ASC
                    LIMIT 1
                    """,
                    (workspace_id, f"%{name.strip()}%", f"%{name.strip()}%"),
                ).fetchone()
                if row:
                    return _row_to_subtree(row)
        return None

    def resolve_subtree_for_create(
        self,
        workspace_id: str,
        *,
        subtree_id: str | None = None,
        subtree_code: str | None = None,
        subtree_name: str | None = None,
        subtree_path: str | None = None,
        topic: str | None = None,
        create_missing: bool = True,
    ) -> SubtreeRecord | None:
        """Resolve subtree for Todo create.

        Prefer explicit id/code/name/path. Name/path may be hierarchical
        (``硬件/主控板/EMI``); missing L2+ nodes can be auto-created under an
        existing L1. New L1 roots are never invented.
        """
        self.ensure_subtrees_for_workspace(workspace_id)
        if subtree_id:
            found = self.find_subtree(workspace_id, subtree_id=subtree_id)
            if found:
                return found
        path_text = (subtree_path or "").strip() or None
        if path_text is None and subtree_name and any(sep in subtree_name for sep in ("/", ">", "→")):
            path_text = subtree_name
        if path_text:
            return self.ensure_subtree_name_path(workspace_id, path_text, create_missing=create_missing)
        if subtree_code:
            found = self.find_subtree(workspace_id, code=subtree_code)
            if found:
                return found
            if create_missing and "." in subtree_code:
                return self.ensure_subtree_code_path(workspace_id, subtree_code, create_missing=True)
        if subtree_name:
            found = self.find_subtree(workspace_id, name=subtree_name)
            if found:
                # Existing L3/L2/L1: L1/L2 filled by walking parent_id (see ancestor_chain).
                return found
            # New leaf name only: attach under Topic default node's parent (L2),
            # so L1/L2 come from parent_id chain without writing the full path.
            if create_missing and topic:
                topic_node = None
                code = TOPIC_DEFAULT_SUBTREE_CODE.get(topic)
                if code:
                    topic_node = self.find_subtree(workspace_id, code=code)
                if topic_node is not None:
                    parent = (
                        self.find_subtree(workspace_id, subtree_id=topic_node.parent_id)
                        if topic_node.parent_id
                        else topic_node
                    )
                    if parent is not None and parent.level >= 1:
                        with self._connect() as conn:
                            self._seed_default_subtrees(conn, workspace_id)
                            return self._insert_subtree_child(
                                conn,
                                workspace_id=workspace_id,
                                name=subtree_name.strip(),
                                parent=parent,
                            )
        if topic:
            code = TOPIC_DEFAULT_SUBTREE_CODE.get(topic)
            if code:
                return self.find_subtree(workspace_id, code=code)
        return None

    def list_child_subtrees(
        self,
        workspace_id: str,
        *,
        parent_id: str | None = None,
        parent_code: str | None = None,
        parent_name: str | None = None,
        parent_path: str | None = None,
        recursive: bool = False,
    ) -> tuple[SubtreeRecord | None, list[SubtreeRecord]]:
        """Return (parent, children). parent may be None when listing L1 roots."""
        self.ensure_subtrees_for_workspace(workspace_id)
        parent: SubtreeRecord | None = None
        if parent_path:
            parent = self.ensure_subtree_name_path(workspace_id, parent_path, create_missing=False)
        elif parent_id or parent_code or parent_name:
            parent = self.find_subtree(
                workspace_id,
                subtree_id=parent_id,
                code=parent_code,
                name=parent_name,
            )
            if parent is None and parent_name and any(sep in parent_name for sep in ("/", ">")):
                parent = self.ensure_subtree_name_path(workspace_id, parent_name, create_missing=False)
        with self._connect() as conn:
            if parent is None and not (parent_id or parent_code or parent_name or parent_path):
                rows = conn.execute(
                    """
                    SELECT * FROM org_subtrees
                    WHERE workspace_id = ? AND deleted_at IS NULL AND level = 1
                    ORDER BY sort_order, name
                    """,
                    (workspace_id,),
                ).fetchall()
                return None, [_row_to_subtree(row) for row in rows]
            if parent is None:
                return None, []
            if recursive:
                rows = conn.execute(
                    """
                    SELECT * FROM org_subtrees
                    WHERE workspace_id = ? AND deleted_at IS NULL
                      AND id != ? AND path LIKE ?
                    ORDER BY level, sort_order, name
                    """,
                    (workspace_id, parent.id, parent.path + "%"),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM org_subtrees
                    WHERE workspace_id = ? AND deleted_at IS NULL AND parent_id = ?
                    ORDER BY sort_order, name
                    """,
                    (workspace_id, parent.id),
                ).fetchall()
        return parent, [_row_to_subtree(row) for row in rows]

    def ensure_subtree_name_path(
        self,
        workspace_id: str,
        path_text: str,
        *,
        create_missing: bool = True,
    ) -> SubtreeRecord | None:
        parts = _split_subtree_path(path_text)
        if not parts:
            return None
        with self._connect() as conn:
            self._seed_default_subtrees(conn, workspace_id)
            parent: SubtreeRecord | None = None
            for index, part in enumerate(parts):
                level = index + 1
                found = self._find_child_locked(conn, workspace_id, parent_id=parent.id if parent else None, token=part)
                if found is not None:
                    parent = found
                    continue
                if level == 1 or not create_missing or parent is None:
                    return None if level == 1 else parent
                parent = self._insert_subtree_child(
                    conn,
                    workspace_id=workspace_id,
                    name=part,
                    parent=parent,
                )
            return parent

    def ensure_subtree_code_path(
        self,
        workspace_id: str,
        code_path: str,
        *,
        create_missing: bool = True,
    ) -> SubtreeRecord | None:
        parts = [p.strip() for p in code_path.split(".") if p.strip()]
        if not parts:
            return None
        with self._connect() as conn:
            self._seed_default_subtrees(conn, workspace_id)
            parent: SubtreeRecord | None = None
            built: list[str] = []
            for index, part in enumerate(parts):
                built.append(part)
                code = ".".join(built)
                row = conn.execute(
                    """
                    SELECT * FROM org_subtrees
                    WHERE workspace_id = ? AND code = ? AND deleted_at IS NULL
                    """,
                    (workspace_id, code),
                ).fetchone()
                if row:
                    parent = _row_to_subtree(row)
                    continue
                if index == 0 or not create_missing or parent is None:
                    return None
                parent = self._insert_subtree_child(
                    conn,
                    workspace_id=workspace_id,
                    name=part,
                    parent=parent,
                    code=code,
                )
            return parent

    def subtree_label(self, subtree_id: str) -> str | None:
        with self._connect() as conn:
            labels = self._subtree_label_map(conn)
        return labels.get(subtree_id)

    def _find_child_locked(
        self,
        conn: sqlite3.Connection,
        workspace_id: str,
        *,
        parent_id: str | None,
        token: str,
    ) -> SubtreeRecord | None:
        token = token.strip()
        if parent_id is None:
            row = conn.execute(
                """
                SELECT * FROM org_subtrees
                WHERE workspace_id = ? AND deleted_at IS NULL AND level = 1
                  AND (name = ? OR code = ? OR id = ?)
                """,
                (workspace_id, token, token, token),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM org_subtrees
                WHERE workspace_id = ? AND deleted_at IS NULL AND parent_id = ?
                  AND (name = ? OR code = ? OR id = ? OR code LIKE ?)
                """,
                (workspace_id, parent_id, token, token, token, f"%.{token}"),
            ).fetchone()
        return _row_to_subtree(row) if row else None

    def _insert_subtree_child(
        self,
        conn: sqlite3.Connection,
        *,
        workspace_id: str,
        name: str,
        parent: SubtreeRecord,
        code: str | None = None,
    ) -> SubtreeRecord:
        slug = _slugify(name)
        node_code = code or f"{parent.code}.{slug}"
        node_id = "st_" + node_code.replace(".", "_")
        # Avoid collisions on re-run
        existing = conn.execute(
            "SELECT * FROM org_subtrees WHERE workspace_id = ? AND (id = ? OR code = ?)",
            (workspace_id, node_id, node_code),
        ).fetchone()
        if existing:
            return _row_to_subtree(existing)
        now = _utcnow().isoformat()
        path = f"{parent.path}{node_id}/"
        level = parent.level + 1
        conn.execute(
            """
            INSERT INTO org_subtrees (
                id, workspace_id, code, name, level, parent_id, path, sort_order,
                status, owner_email, description, metadata_json, created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 100, 'active', NULL, NULL, NULL, ?, ?, NULL)
            """,
            (node_id, workspace_id, node_code, name, level, parent.id, path, now, now),
        )
        row = conn.execute(
            "SELECT * FROM org_subtrees WHERE workspace_id = ? AND id = ?",
            (workspace_id, node_id),
        ).fetchone()
        return _row_to_subtree(row)

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
                    subtree_id TEXT,
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

                CREATE TABLE IF NOT EXISTS org_subtrees (
                    id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    parent_id TEXT,
                    path TEXT NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    owner_email TEXT,
                    description TEXT,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT,
                    PRIMARY KEY (workspace_id, id)
                );

                CREATE INDEX IF NOT EXISTS idx_org_subtrees_parent
                    ON org_subtrees (workspace_id, parent_id);
                CREATE INDEX IF NOT EXISTS idx_org_subtrees_code
                    ON org_subtrees (workspace_id, code);

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
            self._migrate_todo_columns(conn)
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_todos_subtree
                    ON traceforge_todos (workspace_id, subtree_id)
                """
            )
            workspace_ids = {
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT workspace_id FROM traceforge_todos"
                ).fetchall()
            }
            workspace_ids.add("default")
            workspace_ids.add("demo")
            for workspace_id in workspace_ids:
                self._seed_default_subtrees(conn, workspace_id)
            self._backfill_todo_subtrees(conn)

    def _migrate_todo_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(traceforge_todos)").fetchall()}
        if "subtree_id" not in cols:
            conn.execute("ALTER TABLE traceforge_todos ADD COLUMN subtree_id TEXT")

    def _seed_default_subtrees(self, conn: sqlite3.Connection, workspace_id: str) -> None:
        now = _utcnow().isoformat()
        for seed in DEFAULT_SUBTREE_SEEDS:
            conn.execute(
                """
                INSERT INTO org_subtrees (
                    id, workspace_id, code, name, level, parent_id, path, sort_order,
                    status, owner_email, description, metadata_json, created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL, ?, NULL, ?, ?, NULL)
                ON CONFLICT(workspace_id, id) DO UPDATE SET
                    code = excluded.code,
                    name = excluded.name,
                    level = excluded.level,
                    parent_id = excluded.parent_id,
                    path = excluded.path,
                    sort_order = excluded.sort_order,
                    description = excluded.description,
                    updated_at = excluded.updated_at
                """,
                (
                    seed.id,
                    workspace_id,
                    seed.code,
                    seed.name,
                    seed.level,
                    seed.parent_id,
                    seed.path,
                    seed.sort_order,
                    seed.description,
                    now,
                    now,
                ),
            )

    def _backfill_todo_subtrees(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT id, workspace_id, topic, subtree_id
            FROM traceforge_todos
            WHERE deleted_at IS NULL AND (subtree_id IS NULL OR subtree_id = '')
            """
        ).fetchall()
        for row in rows:
            workspace_id = row["workspace_id"] or "default"
            self._seed_default_subtrees(conn, workspace_id)
            code = TOPIC_DEFAULT_SUBTREE_CODE.get(row["topic"] or "", DEFAULT_SUBTREE_FALLBACK_CODE)
            subtree = conn.execute(
                """
                SELECT id FROM org_subtrees
                WHERE workspace_id = ? AND code = ? AND deleted_at IS NULL
                """,
                (workspace_id, code),
            ).fetchone()
            if subtree is None:
                subtree = conn.execute(
                    """
                    SELECT id FROM org_subtrees
                    WHERE workspace_id = ? AND code = ? AND deleted_at IS NULL
                    """,
                    (workspace_id, DEFAULT_SUBTREE_FALLBACK_CODE),
                ).fetchone()
            if subtree is None:
                continue
            conn.execute(
                "UPDATE traceforge_todos SET subtree_id = ? WHERE id = ?",
                (subtree["id"], row["id"]),
            )

    def _subtree_label_map(self, conn: sqlite3.Connection) -> dict[str, str]:
        rows = conn.execute(
            """
            SELECT id, workspace_id, name, path
            FROM org_subtrees
            WHERE deleted_at IS NULL
            """
        ).fetchall()
        by_key = {(row["workspace_id"], row["id"]): row for row in rows}
        labels: dict[str, str] = {}
        for row in rows:
            parts: list[str] = []
            path_ids = [part for part in str(row["path"]).split("/") if part]
            for node_id in path_ids:
                node = by_key.get((row["workspace_id"], node_id))
                if node:
                    parts.append(node["name"])
            labels[row["id"]] = " / ".join(parts) if parts else row["name"]
        return labels

    def _attach_subtree_label(
        self,
        todo: TodoRecord,
        labels: dict[str, str] | None = None,
    ) -> TodoRecord:
        if labels is None:
            with self._connect() as conn:
                labels = self._subtree_label_map(conn)
        label = labels.get(todo.subtree_id)
        if label == todo.subtree_label:
            return todo
        return TodoRecord(
            id=todo.id,
            title=todo.title,
            description=todo.description,
            status=todo.status,
            priority=todo.priority,
            workspace_id=todo.workspace_id,
            subtree_id=todo.subtree_id,
            channel_name=todo.channel_name,
            topic=todo.topic,
            proposer_name=todo.proposer_name,
            proposer_email=todo.proposer_email,
            assignee_name=todo.assignee_name,
            assignee_email=todo.assignee_email,
            source_message_id=todo.source_message_id,
            created_at=todo.created_at,
            updated_at=todo.updated_at,
            completed_at=todo.completed_at,
            deleted_at=todo.deleted_at,
            subtree_label=label,
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
        "subtree_id": todo.subtree_id,
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


def _row_to_todo(
    row: sqlite3.Row,
    *,
    include_description: bool,
    labels: dict[str, str] | None = None,
) -> TodoRecord:
    keys = set(row.keys())
    description = None
    if include_description and "description" in keys:
        description = row["description"]
    subtree_id = row["subtree_id"] if "subtree_id" in keys and row["subtree_id"] else ""
    label = (labels or {}).get(subtree_id)
    return TodoRecord(
        id=row["id"],
        title=row["title"],
        description=description,
        status=TodoStatus(row["status"]),
        priority=int(row["priority"]),
        workspace_id=row["workspace_id"],
        subtree_id=subtree_id,
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
        subtree_label=label,
    )


def _row_to_subtree(row: sqlite3.Row) -> SubtreeRecord:
    return SubtreeRecord(
        id=row["id"],
        workspace_id=row["workspace_id"],
        code=row["code"],
        name=row["name"],
        level=int(row["level"]),
        parent_id=row["parent_id"],
        path=row["path"],
        sort_order=int(row["sort_order"] or 0),
        status=row["status"] or "active",
        owner_email=row["owner_email"],
        description=row["description"],
        metadata_json=row["metadata_json"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
        deleted_at=datetime.fromisoformat(row["deleted_at"]) if row["deleted_at"] else None,
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_completed_at(
    *,
    existing: TodoRecord,
    next_status: TodoStatus,
    status_provided: bool,
    at: datetime,
    explicit_completed_at: datetime | None = None,
    explicit_completed_at_provided: bool = False,
) -> datetime | None:
    """Resolve completed_at without locking a previous done timestamp."""
    if next_status != TodoStatus.DONE:
        if status_provided and existing.status == TodoStatus.DONE:
            return None
        return existing.completed_at

    if explicit_completed_at_provided:
        return explicit_completed_at
    if status_provided:
        return at
    return existing.completed_at


def _split_subtree_path(text: str) -> list[str]:
    raw = text.strip()
    for sep in ("/", ">", "→", "|"):
        if sep in raw:
            return [part.strip() for part in raw.split(sep) if part.strip()]
    return [raw] if raw else []


def _slugify(text: str) -> str:
    import re

    lowered = text.strip().lower()
    ascii_slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    if ascii_slug:
        return ascii_slug[:40]
    compact = re.sub(r"\s+", "", text.strip())
    digest = abs(hash(compact)) % 10_000_000
    return f"n{digest}"
