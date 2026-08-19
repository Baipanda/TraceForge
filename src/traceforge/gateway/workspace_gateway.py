from __future__ import annotations

from typing import Protocol

from traceforge.application.process_event import ProcessWorkspaceEvent, ProcessedEvent
from traceforge.agent.models import AgentRequest, GatewayResponse, RunStatus
from traceforge.context.zulip import ZulipContextBuilder
from traceforge.core.events import WorkspaceEvent
from traceforge.session.keys import SessionKeyResolver


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
        session_recorder: object | None = None,
    ) -> None:
        self._handler = handler
        self._context_builder = context_builder or ZulipContextBuilder()
        self._session_resolver = session_resolver or SessionKeyResolver()
        self._session_recorder = session_recorder

    def route(self, event: WorkspaceEvent) -> GatewayResponse:
        context = self._context_builder.build(event)
        session_key = self._session_resolver.resolve(context)
        request = AgentRequest(
            event=event,
            session_key=session_key,
            metadata={
                "source": event.source.value,
                "kind": event.kind.value,
                "zulip_context": context.to_dict(),
            },
        )
        if callable(self._session_recorder):
            self._session_recorder(event, session_key)
        if self._handler is None:
            raise RuntimeError("WorkspaceGateway handler is not configured")
        return self._handler.handle(request)
