from traceforge.application.process_event import ProcessWorkspaceEvent
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.gateway.workspace_gateway import EventApplicationHandler, WorkspaceGateway
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository
from traceforge.session.transcript import JsonlSessionStore


def test_gateway_builds_context_and_records_session(tmp_path) -> None:
    repository = SqliteTodoRepository(tmp_path / "traceforge.sqlite3")
    processor = ProcessWorkspaceEvent(repository=repository)
    session_store = JsonlSessionStore(tmp_path / "sessions")
    gateway = WorkspaceGateway(
        handler=EventApplicationHandler(processor),
        session_recorder=repository.record_session,
        session_store=session_store,
    )
    event = WorkspaceEvent(
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
        payload={"text": "列出 todo"},
        external_event_id="35",
    )

    response = gateway.route(event)

    assert response.status.value == "succeeded"
    context_evidence = next(item for item in response.evidence if item["type"] == "agent_context")
    assert context_evidence["session_key"].startswith("zulip:2:stream:42:")

    with repository._connect() as conn:
        row = conn.execute(
            "SELECT session_key FROM traceforge_sessions WHERE workspace_id = ?",
            ("2",),
        ).fetchone()
    assert row is not None
    assert row["session_key"] == context_evidence["session_key"]

    transcript = session_store.load_events(context_evidence["session_key"])
    assert transcript[0].type == "user"
    assert transcript[0].content == "列出 todo"
    assert transcript[-1].type == "assistant"
    assert transcript[-1].content == response.reply_text
