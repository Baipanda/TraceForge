from __future__ import annotations

from traceforge.application.process_event import ProcessWorkspaceEvent
from traceforge.application.todo_workflow import TodoWorkflow, parse_todo_command
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.core.todos import TodoAction, TodoFilter, TodoStatus
from traceforge.infrastructure.identity.people_directory import PeopleDirectory
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository


def _event(text: str, topic: str = "SQL 注入排查", email: str = "alice@example.local") -> WorkspaceEvent:
    return WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id=email, display_name="Alice", email=email),
        location=WorkspaceLocation(
            workspace_id="demo",
            channel_id="42",
            channel_name="security",
            topic=topic,
        ),
        payload={"text": text},
        external_event_id="zulip-message-1001",
    )


def test_parse_todo_command_detects_create_title() -> None:
    command = parse_todo_command("@Jarvis 给李四发布一个 todo：检查认证模块 SQL 注入风险")

    assert command.action == TodoAction.CREATE
    assert "检查认证模块 SQL 注入风险" in (command.title or "")
    assert command.assignee_name == "李四"


def test_parse_todo_command_trims_metadata_from_title() -> None:
    command = parse_todo_command(
        "给 Neymar 发布一个 todo：todo 发布测试。发布者是TraceForge Admin，执行人是Neyma @Jarvis"
    )

    assert command.action == TodoAction.CREATE
    assert command.title == "todo 发布测试"


def test_people_directory_resolves_neymar() -> None:
    people = PeopleDirectory()

    record = people.resolve("Neymar")

    assert record is not None
    assert record.email == "neymar@traceforge.local"
    assert record.database_username == "neymar"


def test_todo_repository_create_and_list(tmp_path) -> None:
    repo = SqliteTodoRepository(tmp_path / "traceforge.sqlite3")
    workflow = TodoWorkflow(repo)

    created = workflow.handle(
        _event("给 Neymar 发布一个 todo：检查认证模块 SQL 注入风险"),
        parse_todo_command("给 Neymar 发布一个 todo：检查认证模块 SQL 注入风险"),
    )
    listed = workflow.handle(_event("列出 todo"), parse_todo_command("列出 todo"))

    assert created.todo is not None
    assert created.todo.title == "检查认证模块 SQL 注入风险"
    assert created.todo.proposer_email == "alice@example.local"
    assert created.todo.assignee_email == "neymar@traceforge.local"
    assert "发布者" in created.reply_text
    assert "执行者" in created.reply_text
    assert listed.todos
    assert listed.todos[0].id == created.todo.id


def test_todo_create_requires_assignee(tmp_path) -> None:
    repo = SqliteTodoRepository(tmp_path / "traceforge.sqlite3")
    workflow = TodoWorkflow(repo)

    result = workflow.handle(
        _event("发布一个 todo：检查认证模块 SQL 注入风险"),
        parse_todo_command("发布一个 todo：检查认证模块 SQL 注入风险"),
    )

    assert result.todo is None
    assert "需要指定执行者" in result.reply_text
    assert not repo.list_todos(TodoFilter(workspace_id="demo"))


def test_process_workspace_event_routes_todo_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TRACEFORGE_DB_PATH", str(tmp_path / "traceforge.sqlite3"))
    processor = ProcessWorkspaceEvent()
    event = _event("总结一下当前 todo", topic="SQL 注入排查")

    result = processor.execute(event)

    assert result.intent == "todo.summary"
    assert "Todo Summary" in result.reply_text
