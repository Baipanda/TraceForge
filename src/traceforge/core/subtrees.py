from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class SubtreeRecord:
    id: str
    workspace_id: str
    code: str
    name: str
    level: int
    parent_id: str | None
    path: str
    sort_order: int = 0
    status: str = "active"
    owner_email: str | None = None
    description: str | None = None
    metadata_json: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "code": self.code,
            "name": self.name,
            "level": self.level,
            "parent_id": self.parent_id,
            "path": self.path,
            "sort_order": self.sort_order,
            "status": self.status,
            "owner_email": self.owner_email,
            "description": self.description,
        }


# Zulip Topic → default subtree id (same ids across workspaces via code seed).
TOPIC_DEFAULT_SUBTREE_CODE: dict[str, str] = {
    "football": "other.football",
    "agent开发": "software.cloud.agent",
    "security-review": "software.cloud.agent",
    "sprint-planning": "software.cloud.agent",
}

DEFAULT_SUBTREE_FALLBACK_CODE = "other"
