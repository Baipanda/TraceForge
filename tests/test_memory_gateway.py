from traceforge.agent.models import GatewayResponse, RunStatus
from traceforge.context.zulip import ZulipContextBuilder
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.gateway.workspace_gateway import WorkspaceGateway
from traceforge.infrastructure.storage.memory_repository import SqliteMemoryRepository
from traceforge.memory.service import MemoryService


class _RecordingHandler:
    def __init__(self) -> None:
        self.request = None

    def handle(self, request):
        self.request = request
        return GatewayResponse(
            request_id=request.request_id,
            run_id="run-1",
            reply_text="ok",
            status=RunStatus.SUCCEEDED,
            evidence=[],
        )


def _event() -> WorkspaceEvent:
    return WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(
            external_id="9",
            display_name="TraceForge Admin",
            email="user9@traceforge.local",
        ),
        location=WorkspaceLocation(
            workspace_id="2",
            channel_id="42",
            channel_name="security",
            topic="SQL 注入排查",
        ),
        payload={"text": "@Jarvis 总结一下"},
        external_event_id="35",
    )


def test_gateway_injects_memory_context(tmp_path) -> None:
    repository = SqliteMemoryRepository(tmp_path / "traceforge.sqlite3")
    memory_service = MemoryService(repository)
    event = _event()
    session_key = "zulip:2:stream:42:topic:sql%20注入排查"
    memory_service.record_turn(
        event,
        session_key,
        GatewayResponse(
            request_id="req-1",
            run_id="run-1",
            reply_text="已创建 todo",
            status=RunStatus.SUCCEEDED,
        ),
        conversation=ZulipContextBuilder().build(event),
        request_id="req-1",
    )

    handler = _RecordingHandler()
    gateway = WorkspaceGateway(handler=handler, memory_service=memory_service)

    response = gateway.route(event)

    assert response.reply_text == "ok"
    assert handler.request is not None
    assert handler.request.metadata["memory_context_items"]
