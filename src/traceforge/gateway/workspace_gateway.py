from __future__ import annotations

from typing import Protocol

from traceforge.agent.models import AgentRequest, GatewayResponse
from traceforge.domain.events import WorkspaceEvent


class AgentRequestHandler(Protocol):
    def handle(self, request: AgentRequest) -> GatewayResponse:
        ...


class WorkspaceGateway:
    """TraceForge 的统一入口和路由层。

    当前只定义边界，不替换已有 HTTP/bridge 处理路径。
    后续由这里负责 session、权限、skill/agent 路由和审计入口。
    """

    def __init__(self, handler: AgentRequestHandler | None = None) -> None:
        self._handler = handler

    def route(self, event: WorkspaceEvent) -> GatewayResponse:
        request = AgentRequest(
            event=event,
            session_key=event.route_key(),
            metadata={"source": event.source.value, "kind": event.kind.value},
        )
        if self._handler is None:
            raise RuntimeError("WorkspaceGateway handler is not configured")
        return self._handler.handle(request)
