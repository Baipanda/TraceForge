from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from traceforge.agent.models import ContextItem


class MemoryKind(StrEnum):
    SUMMARY = "summary"
    FACT = "fact"
    DECISION = "decision"
    PREFERENCE = "preference"
    ENTITY = "entity"
    TASK = "task"


class MemoryScope(StrEnum):
    SESSION = "session"
    TOPIC = "topic"
    ACTOR = "actor"
    WORKSPACE = "workspace"
    GLOBAL = "global"


@dataclass(frozen=True)
class MemoryScopeRef:
    scope: MemoryScope
    scope_key: str


@dataclass(frozen=True)
class MemoryEntry:
    memory_key: str
    workspace_id: str
    kind: MemoryKind
    scope: MemoryScope
    scope_key: str
    title: str
    content: str
    source: str = "system"
    source_event_id: str | None = None
    source_request_id: str | None = None
    source_message_id: str | None = None
    confidence: float = 0.8
    importance: int = 0
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    deleted_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_key": self.memory_key,
            "workspace_id": self.workspace_id,
            "kind": self.kind.value,
            "scope": self.scope.value,
            "scope_key": self.scope_key,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "source_event_id": self.source_event_id,
            "source_request_id": self.source_request_id,
            "source_message_id": self.source_message_id,
            "confidence": self.confidence,
            "importance": self.importance,
            "tags": list(self.tags),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_accessed_at": self.last_accessed_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

    def to_context_item(self) -> ContextItem:
        tag_text = f"\n标签: {', '.join(self.tags)}" if self.tags else ""
        metadata = f"\n元数据: {self.metadata}" if self.metadata else ""
        return ContextItem(
            source=f"memory/{self.scope.value}/{self.kind.value}",
            content=(
                f"{self.title}\n{self.content}\n"
                f"来源: {self.source}\n"
                f"置信度: {self.confidence:.2f}\n"
                f"重要性: {self.importance}{tag_text}{metadata}"
            ).strip(),
            metadata=self.to_dict(),
        )


@dataclass(frozen=True)
class MemorySearchRequest:
    workspace_id: str
    scope_refs: tuple[MemoryScopeRef, ...] = ()
    text: str = ""
    kinds: tuple[MemoryKind, ...] = (
        MemoryKind.SUMMARY,
        MemoryKind.FACT,
        MemoryKind.DECISION,
        MemoryKind.PREFERENCE,
        MemoryKind.ENTITY,
        MemoryKind.TASK,
    )
    limit: int = 8

