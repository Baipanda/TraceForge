from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class TodoAction(StrEnum):
    CREATE = "create"
    LIST = "list"
    UPDATE = "update"
    DELETE = "delete"
    SUMMARY = "summary"
    SUBTREE_CHILDREN = "subtree_children"
    SUBTREE_TODOS = "subtree_todos"
    UNKNOWN = "unknown"


class TodoStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELED = "canceled"


@dataclass(frozen=True)
class TodoRecord:
    id: str
    title: str
    description: str | None
    status: TodoStatus
    priority: int
    workspace_id: str
    subtree_id: str
    channel_name: str | None
    topic: str | None
    proposer_name: str | None
    proposer_email: str | None
    assignee_name: str | None
    assignee_email: str | None
    source_message_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    deleted_at: datetime | None = None
    subtree_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "priority": self.priority,
            "workspace_id": self.workspace_id,
            "subtree_id": self.subtree_id,
            "subtree_label": self.subtree_label,
            "channel_name": self.channel_name,
            "topic": self.topic,
            "proposer_name": self.proposer_name,
            "proposer_email": self.proposer_email,
            "assignee_name": self.assignee_name,
            "assignee_email": self.assignee_email,
            "source_message_id": self.source_message_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }
        if self.description is not None:
            data["description"] = self.description
        return data


@dataclass(frozen=True)
class TodoFilter:
    """Queryable Todo fields.

    Add optional columns here as the schema grows; repository applies only
    non-None fields so filters stay backward compatible.
    """

    workspace_id: str | None = None
    status: TodoStatus | None = None
    assignee_email: str | None = None
    assignee_name: str | None = None
    proposer_email: str | None = None
    proposer_name: str | None = None
    topic: str | None = None
    channel_name: str | None = None
    priority: int | None = None
    title_contains: str | None = None
    subtree_id: str | None = None
    subtree_code: str | None = None
    subtree_path_prefix: str | None = None
    include_descendants: bool = True
    include_description: bool = False
    limit: int = 20


@dataclass(frozen=True)
class TodoCommand:
    action: TodoAction
    raw_text: str
    title: str | None = None
    description: str | None = None
    todo_id: str | None = None
    match_title: str | None = None
    match_assignee_name: str | None = None
    match_assignee_email: str | None = None
    assignee_name: str | None = None
    assignee_email: str | None = None
    proposer_name: str | None = None
    proposer_email: str | None = None
    status: TodoStatus | None = None
    priority: int = 0
    topic: str | None = None
    channel_name: str | None = None
    title_contains: str | None = None
    query_text: str | None = None
    group_by: str | None = None
    completed_at: datetime | None = None
    subtree_id: str | None = None
    subtree_code: str | None = None
    subtree_name: str | None = None
    subtree_path: str | None = None
    include_descendants: bool = True
    include_description: bool = False
