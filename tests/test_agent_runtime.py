from pathlib import Path

from traceforge.agent.models import AgentRequest, ModelToolCall, ModelTurn
from traceforge.agent.runtime import AgentRuntime
from traceforge.application.process_event import ProcessWorkspaceEvent
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository


class FakeToolCallingModel:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system_prompt, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return ModelTurn(
                tool_calls=[
                    ModelToolCall(
                        call_id="call_1",
                        name="todo.create",
                        arguments={
                            "title": "检查认证模块",
                            "assignee_name": "Neymar",
                            "subtree_code": "software",
                        },
                    )
                ]
            )
        return ModelTurn(content="已根据工具结果完成处理。")


def test_runtime_executes_tool_then_returns_final_answer(tmp_path) -> None:
    repository = SqliteTodoRepository(Path(tmp_path) / "traceforge.sqlite3")
    processor = ProcessWorkspaceEvent(repository=repository)
    runtime = AgentRuntime(
        tool_registry=processor.tool_registry,
        model=FakeToolCallingModel(),
        max_steps=3,
    )
    event = WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef("9", "TraceForge Admin", "user9@traceforge.local"),
        location=WorkspaceLocation(
            workspace_id="2",
            channel_id="42",
            channel_name="security",
            topic="auth",
        ),
        payload={"text": "给 Neymar 创建一个 todo：检查认证模块"},
        external_event_id="runtime-1",
    )

    response = runtime.handle(
        AgentRequest(
            event=event,
            session_key="zulip:2:stream:42:topic:auth",
        )
    )

    assert any(item["type"] == "tool_call" and item["ok"] for item in response.evidence)
    assert "检查认证模块" in response.reply_text or response.reply_text == "已根据工具结果完成处理。"
    with repository._connect() as conn:
        row = conn.execute(
            "SELECT title, assignee_email, proposer_email FROM traceforge_todos"
        ).fetchone()
    assert row["title"] == "检查认证模块"
    assert row["assignee_email"] == "neymar@traceforge.local"
    assert row["proposer_email"] == "user9@traceforge.local"
