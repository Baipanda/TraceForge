from __future__ import annotations

from traceforge.agent.harness import PromptHarness
from traceforge.agent.models import AgentRequest
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.memory.markdown_index import MarkdownMemoryIndex
from traceforge.memory.markdown_store import MarkdownMemoryStore


def test_markdown_memory_index_search_and_preference_inject(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "memory" / "preferences").mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("# Core\n\nworkspace rule\n", encoding="utf-8")
    (workspace / "memory" / "DECISION.md").write_text(
        "# Decisions\n\n## Auth\n\n采用 OAuth2 作为登录方案。\n",
        encoding="utf-8",
    )
    store = MarkdownMemoryStore(workspace)
    store.append_preference("person-a", "家乡在山东泰安", source="test")
    index = MarkdownMemoryIndex(tmp_path / "mem.sqlite3", store)

    hits = index.search("OAuth2", kinds=("decision",))
    assert hits
    assert "OAuth2" in hits[0].content

    pref_hits = index.search("泰安", kinds=("preference",), person_id="person-a")
    assert pref_hits

    harness = PromptHarness(workspace, memory_store=store)
    bundle = harness.build(
        AgentRequest(
            event=WorkspaceEvent(
                source=EventSource.ZULIP,
                kind=EventKind.MESSAGE_CREATED,
                actor=ActorRef(
                    external_id="9",
                    display_name="Neymar",
                    email="neymar@traceforge.local",
                    person_id="person-a",
                ),
                location=WorkspaceLocation(workspace_id="default", topic="t"),
                payload={"text": "你好"},
            ),
            session_key="zulip:default:stream:1:topic:t",
        )
    )
    assert "山东泰安" in bundle.system_prompt
    assert any(item.source == "memory/preference" for item in bundle.context_items)

    other = harness.build(
        AgentRequest(
            event=WorkspaceEvent(
                source=EventSource.ZULIP,
                kind=EventKind.MESSAGE_CREATED,
                actor=ActorRef(
                    external_id="11",
                    display_name="Peter",
                    email="peter@traceforge.local",
                    person_id="person-b",
                ),
                location=WorkspaceLocation(workspace_id="default", topic="t"),
                payload={"text": "你好"},
            ),
            session_key="zulip:default:stream:1:topic:t",
        )
    )
    assert "山东泰安" not in other.system_prompt


def test_memory_remember_reindexes(tmp_path) -> None:
    from traceforge.tools.memory_tools import register_memory_tools
    from traceforge.tools.models import ToolCall
    from traceforge.tools.registry import ToolRegistry

    workspace = tmp_path / "workspace"
    store = MarkdownMemoryStore(workspace)
    index = MarkdownMemoryIndex(tmp_path / "mem.sqlite3", store)
    registry = ToolRegistry()
    register_memory_tools(registry, index=index, store=store)

    result = registry.call(
        ToolCall(
            name="memory.remember",
            arguments={"person_id": "pid-1", "note": "以后默认用中文回复"},
        )
    )
    assert result.ok
    hits = index.search("中文", kinds=("preference",), person_id="pid-1")
    assert hits
