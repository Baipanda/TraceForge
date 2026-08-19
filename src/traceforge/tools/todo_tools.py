from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from traceforge.application.todo_workflow import TodoWorkflow
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.core.todos import TodoAction, TodoCommand, TodoStatus
from traceforge.infrastructure.identity.people_directory import PeopleDirectory
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry
from traceforge.tools.people_tools import register_people_tools


def build_default_tool_registry(
    repository: SqliteTodoRepository,
    workflow: TodoWorkflow | None = None,
    people_directory: PeopleDirectory | None = None,
) -> ToolRegistry:
    workflow = workflow or TodoWorkflow(repository)
    people_directory = people_directory or PeopleDirectory()
    registry = ToolRegistry()
    register_people_tools(registry, people_directory)
    register_todo_tools(registry, workflow)
    return registry


def register_todo_tools(registry: ToolRegistry, workflow: TodoWorkflow) -> None:
    registry.register(
        RegisteredTool(
            name="todo.create",
            description="Create a TraceForge Todo",
            schema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "channel_name": {"type": "string"},
                    "topic": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "assignee_name": {"type": "string"},
                    "assignee_email": {"type": "string"},
                    "priority": {"type": "integer"},
                },
                "required": ["workspace_id", "title"],
                "anyOf": [
                    {"required": ["assignee_name"]},
                    {"required": ["assignee_email"]},
                ],
            },
            handler=lambda arguments: _create_todo(workflow, arguments),
        )
    )
    registry.register(
        RegisteredTool(
            name="todo.list",
            description="List TraceForge Todos",
            schema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "status": {"type": "string"},
                    "assignee_email": {"type": "string"},
                    "topic": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["workspace_id"],
            },
            handler=lambda arguments: _list_todos(workflow, arguments),
        )
    )
    registry.register(
        RegisteredTool(
            name="todo.update",
            description="Update a TraceForge Todo",
            schema={
                "type": "object",
                "properties": {
                    "todo_id": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string"},
                    "priority": {"type": "integer"},
                    "assignee_name": {"type": "string"},
                    "assignee_email": {"type": "string"},
                },
                "required": ["todo_id"],
            },
            handler=lambda arguments: _update_todo(workflow, arguments),
        )
    )
    registry.register(
        RegisteredTool(
            name="todo.delete",
            description="Delete a TraceForge Todo",
            schema={
                "type": "object",
                "properties": {"todo_id": {"type": "string"}},
                "required": ["todo_id"],
            },
            handler=lambda arguments: _delete_todo(workflow, arguments),
        )
    )
    registry.register(
        RegisteredTool(
            name="todo.summary",
            description="Summarize TraceForge Todos",
            schema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "status": {"type": "string"},
                    "assignee_email": {"type": "string"},
                    "topic": {"type": "string"},
                },
                "required": ["workspace_id"],
            },
            handler=lambda arguments: _summary_todos(workflow, arguments),
        )
    )


def _create_todo(workflow: TodoWorkflow, arguments: dict[str, Any]) -> ToolResult:
    event = _event_from_tool(arguments)
    command = TodoCommand(
        action=TodoAction.CREATE,
        raw_text=str(arguments.get("description") or arguments.get("title") or ""),
        title=str(arguments.get("title") or ""),
        description=arguments.get("description"),
        assignee_name=arguments.get("assignee_name"),
        assignee_email=arguments.get("assignee_email"),
        topic=arguments.get("topic"),
        priority=int(arguments.get("priority") or 0),
    )
    result = workflow.handle(event, command)
    return ToolResult(
        tool_name="todo.create",
        ok=result.todo is not None,
        data={"reply_text": result.reply_text, "todo": result.todo.to_dict() if result.todo else None},
        error=None if result.todo else result.reply_text,
        evidence=result.evidence,
    )


def _list_todos(workflow: TodoWorkflow, arguments: dict[str, Any]) -> ToolResult:
    event = _event_from_tool(arguments)
    status = _parse_status(arguments.get("status"))
    command = TodoCommand(
        action=TodoAction.LIST,
        raw_text=str(arguments),
        status=status,
        assignee_email=arguments.get("assignee_email"),
        topic=arguments.get("topic"),
    )
    result = workflow.handle(event, command)
    return ToolResult(
        tool_name="todo.list",
        ok=True,
        data={
            "reply_text": result.reply_text,
            "todos": [item.to_dict() for item in result.todos],
        },
        evidence=result.evidence,
    )


def _update_todo(workflow: TodoWorkflow, arguments: dict[str, Any]) -> ToolResult:
    event = _event_from_tool(arguments)
    command = TodoCommand(
        action=TodoAction.UPDATE,
        raw_text=str(arguments),
        todo_id=str(arguments.get("todo_id") or ""),
        title=arguments.get("title"),
        description=arguments.get("description"),
        status=_parse_status(arguments.get("status")),
        priority=int(arguments["priority"]) if arguments.get("priority") is not None else 0,
        assignee_name=arguments.get("assignee_name"),
        assignee_email=arguments.get("assignee_email"),
    )
    result = workflow.handle(event, command)
    return ToolResult(
        tool_name="todo.update",
        ok=result.todo is not None,
        data={"reply_text": result.reply_text, "todo": result.todo.to_dict() if result.todo else None},
        error=None if result.todo else result.reply_text,
        evidence=result.evidence,
    )


def _delete_todo(workflow: TodoWorkflow, arguments: dict[str, Any]) -> ToolResult:
    event = _event_from_tool(arguments)
    command = TodoCommand(
        action=TodoAction.DELETE,
        raw_text=str(arguments),
        todo_id=str(arguments.get("todo_id") or ""),
    )
    result = workflow.handle(event, command)
    return ToolResult(
        tool_name="todo.delete",
        ok=result.todo is not None,
        data={"reply_text": result.reply_text, "todo": result.todo.to_dict() if result.todo else None},
        error=None if result.todo else result.reply_text,
        evidence=result.evidence,
    )


def _summary_todos(workflow: TodoWorkflow, arguments: dict[str, Any]) -> ToolResult:
    event = _event_from_tool(arguments)
    command = TodoCommand(
        action=TodoAction.SUMMARY,
        raw_text=str(arguments),
        status=_parse_status(arguments.get("status")),
        assignee_email=arguments.get("assignee_email"),
        topic=arguments.get("topic"),
    )
    result = workflow.handle(event, command)
    return ToolResult(
        tool_name="todo.summary",
        ok=True,
        data={"reply_text": result.reply_text, "todos": [item.to_dict() for item in result.todos]},
        evidence=result.evidence,
    )


def _event_from_tool(arguments: dict[str, Any]) -> WorkspaceEvent:
    workspace_id = str(arguments.get("workspace_id") or "default")
    channel_name = arguments.get("channel_name")
    topic = arguments.get("topic")
    return WorkspaceEvent(
        source=_source_from(arguments),
        kind=_kind_from(arguments),
        actor=_actor_from(arguments),
        location=_location_from(arguments, workspace_id=workspace_id, channel_name=channel_name, topic=topic),
        payload={"text": str(arguments.get("raw_text") or arguments.get("description") or arguments.get("title") or "")},
        external_event_id=arguments.get("external_event_id"),
        occurred_at=_parse_time(arguments.get("occurred_at")),
    )


def _source_from(arguments: dict[str, Any]) -> Any:
    value = str(arguments.get("source") or EventSource.SYSTEM.value)
    return EventSource(value) if value in EventSource._value2member_map_ else EventSource.SYSTEM


def _kind_from(arguments: dict[str, Any]) -> Any:
    value = str(arguments.get("kind") or EventKind.MESSAGE_CREATED.value)
    return EventKind(value) if value in EventKind._value2member_map_ else EventKind.MESSAGE_CREATED


def _actor_from(arguments: dict[str, Any]) -> Any:
    return ActorRef(
        external_id=str(arguments.get("actor_external_id") or arguments.get("actor_email") or "tool"),
        display_name=arguments.get("actor_name"),
        email=arguments.get("actor_email"),
    )


def _location_from(
    arguments: dict[str, Any],
    *,
    workspace_id: str,
    channel_name: str | None,
    topic: str | None,
) -> Any:
    return WorkspaceLocation(
        workspace_id=workspace_id,
        project_id=arguments.get("project_id"),
        channel_id=arguments.get("channel_id"),
        channel_name=channel_name,
        topic=topic,
    )


def _parse_status(value: Any) -> TodoStatus | None:
    if value is None or value == "":
        return None
    text = str(value)
    try:
        return TodoStatus(text)
    except ValueError:
        lowered = text.lower()
        if lowered in {"done", "finished", "closed"}:
            return TodoStatus.DONE
        if lowered in {"open", "todo"}:
            return TodoStatus.OPEN
        if lowered in {"in_progress", "progress"}:
            return TodoStatus.IN_PROGRESS
        if lowered in {"canceled", "cancelled"}:
            return TodoStatus.CANCELED
        return None


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.now(timezone.utc)
