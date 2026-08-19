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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority,
            "workspace_id": self.workspace_id,
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


@dataclass(frozen=True)
class TodoFilter:
    workspace_id: str
    status: TodoStatus | None = None
    assignee_email: str | None = None
    topic: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class TodoCommand:
    action: TodoAction
    raw_text: str
    title: str | None = None
    description: str | None = None
    todo_id: str | None = None
    assignee_name: str | None = None
    assignee_email: str | None = None
    status: TodoStatus | None = None
    priority: int = 0
    topic: str | None = None
    query_text: str | None = None

