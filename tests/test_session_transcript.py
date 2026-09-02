from __future__ import annotations

from traceforge.agent.harness import PromptHarness
from traceforge.agent.models import AgentRequest
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.session.transcript import (
    JsonlSessionStore,
    SessionEvent,
    build_session_messages,
    estimate_tokens,
)


def _event(text: str = "hello") -> WorkspaceEvent:
    return WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id="9", display_name="Neymar", email="neymar@traceforge.local", person_id="p1"),
        location=WorkspaceLocation(workspace_id="default", channel_name="security", topic="agent开发"),
        payload={"text": text},
    )


def test_jsonl_session_store_roundtrip(tmp_path) -> None:
    store = JsonlSessionStore(tmp_path / "sessions")
    key = "zulip:default:stream:42:topic:agent"
    store.append(key, SessionEvent(type="user", content="第一句", person_id="p1"))
    store.append(key, SessionEvent(type="assistant", content="收到"))

    events = store.load_events(key)

    assert len(events) == 2
    assert events[0].type == "user"
    assert events[0].content == "第一句"
    assert events[1].type == "assistant"


def test_build_session_messages_keeps_recent_token_budget() -> None:
    events = [
        SessionEvent(type="user", content="a" * 100),
        SessionEvent(type="assistant", content="b" * 100),
        SessionEvent(type="user", content="最新用户"),
        SessionEvent(type="assistant", content="最新助手"),
    ]
    messages = build_session_messages(events, keep_recent_tokens=estimate_tokens("最新助手") + 1)

    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "最新助手"
    assert len(messages) <= 2


def test_tool_events_project_as_user_context_not_raw_tool_role() -> None:
    messages = build_session_messages(
        [
            SessionEvent(type="user", content="查记忆"),
            SessionEvent(
                type="tool",
                content='{"tool_name":"memory.search","ok":true}',
                name="memory.search",
                call_id="call-1",
                ok=True,
            ),
            SessionEvent(type="assistant", content="找到了"),
        ]
    )
    assert messages[1]["role"] == "user"
    assert "memory.search" in messages[1]["content"]
    assert all(message["role"] != "tool" for message in messages)


def test_harness_prefixes_session_history() -> None:
    request = AgentRequest(
        event=_event("当前问题"),
        session_key="zulip:demo:stream:1:topic:t",
        session_messages=(
            {"role": "user", "content": "上一句"},
            {"role": "assistant", "content": "上一答"},
        ),
    )
    bundle = PromptHarness().build(request)

    assert bundle.messages[0] == {"role": "user", "content": "上一句"}
    assert bundle.messages[1] == {"role": "assistant", "content": "上一答"}
    assert bundle.messages[-1]["role"] == "user"
    assert "当前问题" in bundle.messages[-1]["content"]
