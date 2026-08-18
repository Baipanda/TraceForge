from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class EventSource(StrEnum):
    ZULIP = "zulip"
    API = "api"
    CLI = "cli"
    SYSTEM = "system"


class EventKind(StrEnum):
    MESSAGE_CREATED = "message.created"
    TODO_CREATED = "todo.created"
    TODO_UPDATED = "todo.updated"
    DOCUMENT_UPDATED = "document.updated"
    REPOSITORY_UPDATED = "repository.updated"
    SECURITY_FINDING_CREATED = "security_finding.created"


@dataclass(frozen=True)
class ActorRef:
    external_id: str
    display_name: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class WorkspaceLocation:
    workspace_id: str
    project_id: str | None = None
    channel_id: str | None = None
    channel_name: str | None = None
    topic: str | None = None


@dataclass(frozen=True)
class WorkspaceEvent:
    source: EventSource
    kind: EventKind
    actor: ActorRef
    location: WorkspaceLocation
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    external_event_id: str | None = None

    def route_key(self) -> str:
        parts = [
            self.source.value,
            self.location.workspace_id,
            self.location.project_id or "_",
            self.location.channel_id or "_",
            self.location.topic or "_",
        ]
        return ":".join(parts)
