from __future__ import annotations

from datetime import datetime, timezone

from traceforge.application.todo_workflow import TodoWorkflow
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.core.todos import TodoAction, TodoCommand, TodoStatus
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository


def _event(*, text: str, occurred_at: datetime, topic: str = "agent开发") -> WorkspaceEvent:
    return WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id="8", display_name="Admin", email="user8@traceforge.local"),
        location=WorkspaceLocation(
            workspace_id="default",
            channel_id="3",
            channel_name="general",
            topic=topic,
        ),
        payload={"text": text, "message_type": "stream"},
        external_event_id="msg-1",
        occurred_at=occurred_at,
    )


def test_done_todo_completion_time_can_be_refreshed(tmp_path) -> None:
    repo = SqliteTodoRepository(tmp_path / "todos.sqlite3")
    workflow = TodoWorkflow(repo)

    created_at = datetime(2026, 8, 25, 20, 5, tzinfo=timezone.utc)
    first_done_at = datetime(2026, 8, 30, 8, 35, 33, tzinfo=timezone.utc)
    later_message_at = datetime(2026, 8, 30, 10, 0, 21, tzinfo=timezone.utc)

    created = workflow.handle(
        _event(text="create", occurred_at=created_at),
        TodoCommand(
            action=TodoAction.CREATE,
            raw_text="create",
            title="起草 memory.search Tool schema-修改测试",
            assignee_name="Neymar",
            topic="agent开发",
        ),
    )
    assert created.todo is not None

    first = workflow.handle(
        _event(text="done", occurred_at=first_done_at),
        TodoCommand(
            action=TodoAction.UPDATE,
            raw_text="这个 todo 完成了",
            match_title="起草 memory.search Tool schema-修改测试",
            status=TodoStatus.DONE,
            topic="agent开发",
        ),
    )
    assert first.todo is not None
    assert first.todo.completed_at == first_done_at

    refreshed = workflow.handle(
        _event(text="refresh", occurred_at=later_message_at),
        TodoCommand(
            action=TodoAction.UPDATE,
            raw_text="修改这个todo的完成时间，为当前zulip中聊天的时间",
            match_title="起草 memory.search Tool schema-修改测试",
            status=TodoStatus.DONE,
            topic="agent开发",
        ),
    )
    assert refreshed.todo is not None
    assert refreshed.todo.completed_at == later_message_at

    explicit_at = datetime(2026, 8, 30, 11, 0, tzinfo=timezone.utc)
    explicit = workflow.handle(
        _event(text="explicit", occurred_at=later_message_at),
        TodoCommand(
            action=TodoAction.UPDATE,
            raw_text="把完成时间改成指定时间",
            match_title="起草 memory.search Tool schema-修改测试",
            completed_at=explicit_at,
            topic="agent开发",
        ),
    )
    assert explicit.todo is not None
    assert explicit.todo.completed_at == explicit_at

    renamed = workflow.handle(
        _event(text="rename", occurred_at=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)),
        TodoCommand(
            action=TodoAction.UPDATE,
            raw_text="改个标题",
            match_title="起草 memory.search Tool schema-修改测试",
            title="起草 memory.search Tool schema-修改测试-v2",
            topic="agent开发",
        ),
    )
    assert renamed.todo is not None
    assert renamed.todo.title.endswith("-v2")
    assert renamed.todo.completed_at == explicit_at
