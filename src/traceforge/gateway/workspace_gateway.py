from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from traceforge.application.process_event import ProcessWorkspaceEvent, ProcessedEvent
from traceforge.agent.models import AgentRequest, GatewayResponse, RunStatus
from traceforge.config import get_settings
from traceforge.context.zulip import ZulipContextBuilder
from traceforge.core.events import WorkspaceEvent
from traceforge.memory.service import MemoryService
from traceforge.session.keys import SessionKeyResolver
from traceforge.session.transcript import (
    DEFAULT_KEEP_RECENT_TOKENS,
    JsonlSessionStore,
    SessionEvent,
    build_session_messages,
)


class AgentRequestHandler(Protocol):
    def handle(self, request: AgentRequest) -> GatewayResponse:
        ...


class EventApplicationHandler:
    """Adapts the current deterministic application path to the Gateway contract."""

    def __init__(self, processor: ProcessWorkspaceEvent | None = None) -> None:
        self.processor = processor or ProcessWorkspaceEvent()

    def handle(self, request: AgentRequest) -> GatewayResponse:
        result: ProcessedEvent = self.processor.execute(request.event)
        evidence = [
            *result.evidence,
            {
                "type": "agent_context",
                "session_key": request.session_key,
                "context": request.metadata.get("zulip_context"),
            },
        ]
        return GatewayResponse(
            request_id=request.request_id,
            run_id=None,
            reply_text=result.reply_text,
            status=RunStatus.SUCCEEDED,
            evidence=evidence,
        )


class WorkspaceGateway:
    """TraceForge 的统一入口、上下文构建和路由层。

    当前阶段仍然把 Todo 路由到确定性 Application。
    后续可以在同一个入口把复杂请求路由到 AgentRuntime。
    """

    def __init__(
        self,
        handler: AgentRequestHandler | None = None,
        *,
        context_builder: ZulipContextBuilder | None = None,
        session_resolver: SessionKeyResolver | None = None,
        session_store: JsonlSessionStore | None = None,
        session_recorder: object | None = None,
        memory_service: MemoryService | None = None,
        keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS,
    ) -> None:
        self._handler = handler
        self._context_builder = context_builder or ZulipContextBuilder()
        self._session_resolver = session_resolver or SessionKeyResolver()
        self._session_store = session_store or JsonlSessionStore(_default_session_root())
        self._session_recorder = session_recorder
        self._memory_service = memory_service
        self._keep_recent_tokens = keep_recent_tokens

    def route(self, event: WorkspaceEvent) -> GatewayResponse:
        context = self._context_builder.build(event)
        session_key = self._session_resolver.resolve(context)
        prior_events = self._session_store.load_events(session_key)
        session_messages = tuple(
            build_session_messages(prior_events, keep_recent_tokens=self._keep_recent_tokens)
        )
        memory_context_items = []
        if self._memory_service is not None:
            memory_context_items = self._memory_service.build_context(event, session_key, context)
        request = AgentRequest(
            event=event,
            session_key=session_key,
            session_messages=session_messages,
            metadata={
                "source": event.source.value,
                "kind": event.kind.value,
                "zulip_context": context.to_dict(),
                "memory_context_items": memory_context_items,
            },
        )
        if callable(self._session_recorder):
            self._session_recorder(event, session_key)
        if self._handler is None:
            raise RuntimeError("WorkspaceGateway handler is not configured")

        # Mirror Zulip user text into the transcript before the agent run (OpenClaw-style).
        user_text = str(event.payload.get("text") or "").strip()
        if user_text:
            self._session_store.append(
                session_key,
                SessionEvent(
                    type="user",
                    content=user_text,
                    person_id=event.actor.person_id,
                ),
            )

        response = self._handler.handle(request)
        self._append_agent_turn(session_key, response)
        if self._memory_service is not None:
            self._memory_service.record_turn(
                event,
                session_key,
                response,
                conversation=context,
                request_id=request.request_id,
            )
        return response

    def _append_agent_turn(self, session_key: str, response: GatewayResponse) -> None:
        events: list[SessionEvent] = []
        for item in response.evidence:
            if not isinstance(item, dict) or item.get("type") != "tool_call":
                continue
            tool_name = str(item.get("tool_name") or "tool")
            ok = bool(item.get("ok"))
            call_id = item.get("call_id")
            content = json.dumps(
                {
                    "tool_name": tool_name,
                    "ok": ok,
                    "error": item.get("error"),
                },
                ensure_ascii=False,
            )
            events.append(
                SessionEvent(
                    type="tool",
                    content=content,
                    name=tool_name,
                    call_id=str(call_id) if call_id else None,
                    ok=ok,
                )
            )
        reply = (response.reply_text or "").strip()
        if reply:
            events.append(SessionEvent(type="assistant", content=reply))
        if events:
            self._session_store.append(session_key, events)


def _default_session_root() -> Path:
    settings = get_settings()
    return Path(settings.traceforge_db_path).expanduser().resolve().parent / "sessions"
