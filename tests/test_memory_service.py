from traceforge.agent.models import GatewayResponse, RunStatus
from traceforge.context.zulip import ZulipContextBuilder
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.infrastructure.storage.memory_repository import SqliteMemoryRepository
from traceforge.memory.models import MemoryKind, MemoryScope
from traceforge.memory.service import MemoryService
from traceforge.session.keys import SessionKeyResolver


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
        payload={"text": "@Jarvis 创建 todo"},
        external_event_id="35",
    )


def test_memory_service_records_session_summary_and_identity(tmp_path) -> None:
    repository = SqliteMemoryRepository(tmp_path / "traceforge.sqlite3")
    service = MemoryService(repository)
    event = _event()
    context = ZulipContextBuilder().build(event)
    session_key = SessionKeyResolver().resolve(context)
    response = GatewayResponse(
        request_id="req-1",
        run_id="run-1",
        reply_text="已创建 todo",
        status=RunStatus.SUCCEEDED,
        evidence=[
            {"type": "intent", "action": "create"},
            {"type": "tool_call", "tool_name": "todo.create"},
        ],
    )

    service.record_turn(
        event,
        session_key,
        response,
        conversation=context,
        request_id="req-1",
    )

    session_entry = repository.get(f"2:session:{session_key}:summary")
    identity_entry = repository.get("2:actor:user9@traceforge.local")

    assert session_entry is not None
    assert session_entry.kind == MemoryKind.SUMMARY
    assert session_entry.scope == MemoryScope.SESSION
    assert identity_entry is not None
    assert identity_entry.scope == MemoryScope.ACTOR


def test_memory_service_build_context_returns_relevant_items(tmp_path) -> None:
    repository = SqliteMemoryRepository(tmp_path / "traceforge.sqlite3")
    service = MemoryService(repository)
    event = _event()
    context = ZulipContextBuilder().build(event)
    session_key = SessionKeyResolver().resolve(context)
    service.record_turn(
        event,
        session_key,
        GatewayResponse(
            request_id="req-1",
            run_id="run-1",
            reply_text="已创建 todo",
            status=RunStatus.SUCCEEDED,
        ),
        conversation=context,
        request_id="req-1",
    )

    items = service.build_context(event, session_key, context)

    assert items
    assert any(item.source.startswith("memory/session") for item in items)
