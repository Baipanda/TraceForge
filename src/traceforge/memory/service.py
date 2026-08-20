from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from traceforge.agent.models import ContextItem, GatewayResponse
from traceforge.context.models import ZulipConversationContext
from traceforge.core.events import WorkspaceEvent
from traceforge.infrastructure.identity.people_directory import PeopleDirectory
from traceforge.memory.models import (
    MemoryEntry,
    MemoryKind,
    MemoryScope,
    MemoryScopeRef,
    MemorySearchRequest,
)
from traceforge.infrastructure.storage.memory_repository import SqliteMemoryRepository


@dataclass(frozen=True)
class MemorySnapshot:
    items: list[ContextItem]
    entries: list[MemoryEntry]


class MemoryService:
    """TraceForge memory orchestration.

    The service turns durable memory entries into prompt context and records
    new session facts after each run.
    """

    def __init__(
        self,
        repository: SqliteMemoryRepository,
        *,
        people_directory: PeopleDirectory | None = None,
        search_limit: int = 8,
    ) -> None:
        self.repository = repository
        self.people_directory = people_directory or PeopleDirectory()
        self.search_limit = search_limit

    def build_context(
        self,
        event: WorkspaceEvent,
        session_key: str,
        conversation: ZulipConversationContext | None = None,
    ) -> list[ContextItem]:
        request = MemorySearchRequest(
            workspace_id=event.location.workspace_id,
            scope_refs=self._scope_refs(event, session_key, conversation),
            text=self._search_text(event, conversation),
            limit=self.search_limit,
        )
        entries = self.repository.search(request)
        return [entry.to_context_item() for entry in entries]

    def record_turn(
        self,
        event: WorkspaceEvent,
        session_key: str,
        response: GatewayResponse,
        *,
        conversation: ZulipConversationContext | None = None,
        request_id: str | None = None,
    ) -> None:
        self._record_identity(event, request_id=request_id)
        self._record_session_summary(
            event,
            session_key,
            response,
            conversation=conversation,
            request_id=request_id,
        )

    def remember_fact(
        self,
        *,
        workspace_id: str,
        scope: MemoryScope,
        scope_key: str,
        title: str,
        content: str,
        kind: MemoryKind = MemoryKind.FACT,
        tags: tuple[str, ...] = (),
        source: str = "manual",
        confidence: float = 0.9,
        importance: int = 0,
        metadata: dict[str, Any] | None = None,
        source_event_id: str | None = None,
        source_request_id: str | None = None,
        source_message_id: str | None = None,
        memory_key: str | None = None,
    ) -> MemoryEntry:
        entry = MemoryEntry(
            memory_key=memory_key or self._default_memory_key(workspace_id, scope, scope_key, title),
            workspace_id=workspace_id,
            kind=kind,
            scope=scope,
            scope_key=scope_key,
            title=title,
            content=content,
            source=source,
            source_event_id=source_event_id,
            source_request_id=source_request_id,
            source_message_id=source_message_id,
            confidence=confidence,
            importance=importance,
            tags=tags,
            metadata=metadata or {},
        )
        self.repository.upsert(entry)
        return entry

    def _record_identity(self, event: WorkspaceEvent, *, request_id: str | None = None) -> None:
        if not event.actor.email and not event.actor.display_name:
            return
        display_name = event.actor.display_name or event.actor.email or event.actor.external_id
        scope_key = event.actor.email or event.actor.external_id
        self.remember_fact(
            workspace_id=event.location.workspace_id,
            scope=MemoryScope.ACTOR,
            scope_key=scope_key,
            title=f"身份映射: {display_name}",
            content=(
                f"Zulip 参与者 {display_name} 的稳定标识。"
                f" external_id={event.actor.external_id}, email={event.actor.email or 'unknown'}."
            ),
            kind=MemoryKind.ENTITY,
            tags=("identity", "zulip"),
            source="zulip",
            confidence=1.0,
            importance=5,
            metadata={
                "display_name": event.actor.display_name,
                "email": event.actor.email,
                "external_id": event.actor.external_id,
            },
            source_event_id=event.event_id,
            source_request_id=request_id,
            source_message_id=event.external_event_id,
            memory_key=f"{event.location.workspace_id}:actor:{scope_key}",
        )

    def _record_session_summary(
        self,
        event: WorkspaceEvent,
        session_key: str,
        response: GatewayResponse,
        *,
        conversation: ZulipConversationContext | None = None,
        request_id: str | None = None,
    ) -> None:
        intent = _intent_from_evidence(response.evidence)
        tool_names = _tool_names_from_evidence(response.evidence)
        summary = "\n".join(
            line
            for line in [
                f"用户消息: {str(event.payload.get('text') or '').strip()}",
                f"助手回复: {response.reply_text.strip()}",
                f"意图: {intent}",
                f"工具: {', '.join(tool_names)}" if tool_names else "",
            ]
            if line
        )
        tags = tuple(
            item
            for item in [
                event.location.channel_name or event.location.channel_id,
                event.location.topic,
                event.actor.email,
            ]
            if item
        )
        self.remember_fact(
            workspace_id=event.location.workspace_id,
            scope=MemoryScope.SESSION,
            scope_key=session_key,
            title="会话摘要",
            content=summary,
            kind=MemoryKind.SUMMARY,
            tags=tags,
            source="agent-run",
            confidence=0.92,
            importance=3,
            metadata={
                "intent": intent,
                "tool_names": tool_names,
                "conversation": conversation.to_dict() if conversation else None,
            },
            source_event_id=event.event_id,
            source_request_id=request_id,
            source_message_id=event.external_event_id,
            memory_key=f"{event.location.workspace_id}:session:{session_key}:summary",
        )

    def _scope_refs(
        self,
        event: WorkspaceEvent,
        session_key: str,
        conversation: ZulipConversationContext | None,
    ) -> tuple[MemoryScopeRef, ...]:
        refs = [
            MemoryScopeRef(MemoryScope.SESSION, session_key),
            MemoryScopeRef(MemoryScope.WORKSPACE, event.location.workspace_id),
        ]
        if event.actor.email:
            refs.append(MemoryScopeRef(MemoryScope.ACTOR, event.actor.email))
        if event.actor.external_id:
            refs.append(MemoryScopeRef(MemoryScope.ACTOR, event.actor.external_id))
        if conversation:
            for participant in conversation.participants:
                if participant.email:
                    refs.append(MemoryScopeRef(MemoryScope.ACTOR, participant.email))
                elif participant.external_id:
                    refs.append(MemoryScopeRef(MemoryScope.ACTOR, participant.external_id))
            for mention in conversation.mentions:
                record = self.people_directory.resolve(mention)
                if record:
                    if record.email:
                        refs.append(MemoryScopeRef(MemoryScope.ACTOR, record.email))
                    if record.database_username:
                        refs.append(MemoryScopeRef(MemoryScope.ACTOR, record.database_username))
        return _unique_scope_refs(refs)

    def _search_text(self, event: WorkspaceEvent, conversation: ZulipConversationContext | None) -> str:
        pieces = [
            str(event.payload.get("text") or ""),
            event.location.topic or "",
            event.location.channel_name or "",
        ]
        if conversation:
            pieces.extend(
                [
                    conversation.sender.display_name or "",
                    conversation.sender.email or "",
                    " ".join(conversation.mentions),
                ]
            )
        return " ".join(piece for piece in pieces if piece).strip()

    def _default_memory_key(self, workspace_id: str, scope: MemoryScope, scope_key: str, title: str) -> str:
        normalized_title = _slugify(title)
        return f"{workspace_id}:{scope.value}:{scope_key}:{normalized_title}"


def _unique_scope_refs(refs: list[MemoryScopeRef]) -> tuple[MemoryScopeRef, ...]:
    seen: set[tuple[str, str]] = set()
    result: list[MemoryScopeRef] = []
    for ref in refs:
        key = (ref.scope.value, ref.scope_key)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return tuple(result)


def _tool_names_from_evidence(evidence: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in evidence:
        tool_name = item.get("tool_name")
        if isinstance(tool_name, str) and tool_name not in names:
            names.append(tool_name)
    return names


def _intent_from_evidence(evidence: list[dict[str, Any]]) -> str:
    for item in evidence:
        if item.get("type") == "intent":
            action = item.get("action")
            if isinstance(action, str):
                return action
    for item in evidence:
        if item.get("type") == "tool_call":
            tool_name = item.get("tool_name")
            if isinstance(tool_name, str):
                return tool_name
    return "agent"


def _slugify(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "-" for character in value.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or "memory"
