from __future__ import annotations

from traceforge.agent.models import AgentRequest, GatewayResponse, RunStatus
from traceforge.application.topic_summary_synthesizer import TopicDigest
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.core.todos import TodoRecord, TodoStatus
from traceforge.gateway.workspace_gateway import WorkspaceGateway
from traceforge.memory.event_writer import MemoryEventWriter
from traceforge.memory.markdown_index import MarkdownMemoryIndex
from traceforge.memory.markdown_store import MarkdownMemoryStore
from traceforge.session.compaction import estimate_transcript_tokens, maybe_flush_and_compact
from traceforge.session.transcript import JsonlSessionStore, SessionEvent, build_session_messages
from datetime import datetime, timezone


def test_compaction_event_projects_into_session_messages() -> None:
    events = [
        SessionEvent(type="compaction", content="先前讨论了鉴权方案", name="session.compact"),
        SessionEvent(type="user", content="继续"),
    ]
    messages = build_session_messages(events, keep_recent_tokens=10_000)
    assert messages[0]["role"] == "assistant"
    assert "鉴权" in messages[0]["content"]


def test_flush_near_threshold_and_compact_over_budget(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    store = JsonlSessionStore(tmp_path / "sessions")
    memory = MarkdownMemoryStore(workspace)
    index = MarkdownMemoryIndex(tmp_path / "mem.sqlite3", memory)
    key = "zulip:default:stream:1:topic:t"

    # Build a transcript large enough to hit a tiny keep budget.
    for i in range(30):
        store.append(key, SessionEvent(type="user", content=f"用户消息 {i} " + ("决定采用方案A " if i == 10 else "x") * 20))
        store.append(key, SessionEvent(type="assistant", content=f"助手回复 {i} " + "y" * 40))

    keep = 80
    before_tokens = estimate_transcript_tokens(store.load_events(key))
    assert before_tokens >= keep

    result = maybe_flush_and_compact(
        session_key=key,
        store=store,
        memory_store=memory,
        memory_index=index,
        keep_recent_tokens=keep,
        summarizer=None,
        topic="agent开发",
        channel_name="security",
    )
    assert result.flushed
    assert result.compacted

    daily = (workspace / "memory").glob("*.md")
    daily_texts = [p.read_text(encoding="utf-8") for p in daily if p.name != "DECISION.md"]
    assert any("session_flush" in text or "session=" in text for text in daily_texts)
    decision = (workspace / "memory" / "DECISION.md").read_text(encoding="utf-8")
    assert "agent开发" in decision or "flush" in decision.lower() or "会话" in decision

    events = store.load_events(key)
    assert events[0].type == "compaction"
    after_tokens = estimate_transcript_tokens(events)
    assert after_tokens < before_tokens


class _EchoHandler:
    def handle(self, request: AgentRequest) -> GatewayResponse:
        return GatewayResponse(
            request_id=request.request_id,
            run_id="r1",
            reply_text="ok",
            status=RunStatus.SUCCEEDED,
            evidence=[],
        )


def test_gateway_runs_compaction_after_turn(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    sessions = tmp_path / "sessions"
    memory = MarkdownMemoryStore(workspace)
    index = MarkdownMemoryIndex(tmp_path / "mem.sqlite3", memory)
    store = JsonlSessionStore(sessions)
    key_prefix_events = []
    for i in range(25):
        key_prefix_events.append(SessionEvent(type="user", content=("提前填充 " + str(i) + " ") * 15))
        key_prefix_events.append(SessionEvent(type="assistant", content=("reply " + str(i) + " ") * 15))

    # Pre-seed one session file by routing once then manually stuffing — easier: append after first resolve.
    gateway = WorkspaceGateway(
        handler=_EchoHandler(),
        session_store=store,
        memory_store=memory,
        memory_index=index,
        keep_recent_tokens=60,
    )
    event = WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id="9", display_name="Neymar", email="n@t.l", person_id="p1"),
        location=WorkspaceLocation(workspace_id="default", channel_name="security", topic="agent开发"),
        payload={"text": "触发压缩"},
    )
    # Seed transcript under the same key the gateway will resolve.
    from traceforge.session.keys import SessionKeyResolver
    from traceforge.context.zulip import ZulipContextBuilder

    session_key = SessionKeyResolver().resolve(ZulipContextBuilder().build(event))
    store.append(session_key, key_prefix_events)

    response = gateway.route(event)
    assert any(item.get("type") == "session.compaction" for item in response.evidence)


def test_memory_event_writer_topic_and_todo(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    store = MarkdownMemoryStore(workspace)
    index = MarkdownMemoryIndex(tmp_path / "mem.sqlite3", store)
    writer = MemoryEventWriter(store, index)

    digest = TopicDigest(
        background="背景",
        confirmed_facts=("事实1",),
        decisions=("采用方案B",),
        open_questions=("还差什么?",),
        risks=(),
        suggested_actions=(),
        key_quotes=(),
    )
    writer.record_topic_summary(
        stream="security",
        topic="agent开发",
        reply_text="ignored",
        digest=digest,
        message_count=12,
        todo_count=2,
    )
    now = datetime.now(timezone.utc)
    todo = TodoRecord(
        id="t1",
        title="修压缩",
        description=None,
        status=TodoStatus.OPEN,
        priority=0,
        workspace_id="default",
        subtree_id="s1",
        channel_name="security",
        topic="agent开发",
        proposer_name="Neymar",
        proposer_email="n@t.l",
        assignee_name="Peter",
        assignee_email="p@t.l",
        source_message_id=None,
        created_at=now,
        updated_at=now,
    )
    writer.record_todo_change(action="create", todo=todo)

    decision = (workspace / "memory" / "DECISION.md").read_text(encoding="utf-8")
    assert "采用方案B" in decision
    assert "修压缩" in decision
    hits = index.search("方案B", kinds=("decision",))
    assert hits
