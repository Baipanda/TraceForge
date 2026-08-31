from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from traceforge.application.todo_workflow import TodoWorkflow
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.core.todos import TodoAction, TodoCommand, TodoStatus
from traceforge.infrastructure.identity.person_store import PersonStore
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry
from traceforge.tools.people_tools import register_people_tools
from traceforge.tools.zulip_tools import register_zulip_tools
from traceforge.config import get_settings


def build_default_tool_registry(
    repository: SqliteTodoRepository,
    workflow: TodoWorkflow | None = None,
    person_store: PersonStore | None = None,
) -> ToolRegistry:
    person_store = person_store or PersonStore(repository.db_path)
    workflow = workflow or TodoWorkflow(repository, person_store=person_store)
    settings = get_settings()
    registry = ToolRegistry()
    register_people_tools(registry, person_store)
    register_todo_tools(registry, workflow)
    register_zulip_tools(registry, repository, settings=settings)
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
                    "description": {
                        "type": "string",
                        "description": "Optional task details; not shown in list unless requested later",
                    },
                    "assignee_name": {"type": "string"},
                    "assignee_email": {"type": "string"},
                    "priority": {"type": "integer"},
                    "subtree_id": {"type": "string"},
                    "subtree_code": {
                        "type": "string",
                        "description": (
                            "Org subtree code, e.g. software.cloud.agent or other.football. "
                            "Required unless Topic maps automatically (agent开发/football/...)."
                        ),
                    },
                    "subtree_name": {
                        "type": "string",
                        "description": "Org subtree display name fragment, e.g. TraceForge Agent",
                    },
                    "subtree_path": {
                        "type": "string",
                        "description": (
                            "Hierarchical name path, e.g. 硬件/主控板/EMI测试. "
                            "Missing L2/L3 nodes are auto-created under an existing L1."
                        ),
                    },
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
            description=(
                "List TraceForge Todos with optional filters. "
                "Description is omitted by default; set include_description=true only when the user asks. "
                "When many rows match, the tool returns a Topic/assignee/status summary "
                "instead of a long detail list. Never show database ids to users."
            ),
            schema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "status": {"type": "string"},
                    "assignee_email": {"type": "string"},
                    "assignee_name": {"type": "string"},
                    "proposer_email": {"type": "string"},
                    "proposer_name": {"type": "string"},
                    "topic": {"type": "string"},
                    "channel_name": {"type": "string"},
                    "priority": {"type": "integer"},
                    "title_contains": {"type": "string"},
                    "include_description": {
                        "type": "boolean",
                        "description": "Include description column only when user explicitly asks",
                    },
                    "subtree_code": {"type": "string"},
                    "subtree_name": {"type": "string"},
                    "subtree_path": {"type": "string"},
                    "include_descendants": {
                        "type": "boolean",
                        "description": "When filtering by subtree, include descendant nodes (default true)",
                    },
                    "group_by": {
                        "type": "string",
                        "description": "Force summary grouping: topic | assignee | status",
                    },
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
            description=(
                "Update a TraceForge Todo. Locate with match_title / match_assignee_* / topic; "
                "do not ask users for database ids. Patch title/status/assignee/priority/description."
            ),
            schema={
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "string",
                        "description": "Internal only if already known from a prior tool result _internal_id",
                    },
                    "match_title": {"type": "string"},
                    "match_assignee_name": {"type": "string"},
                    "match_assignee_email": {"type": "string"},
                    "topic": {"type": "string"},
                    "channel_name": {"type": "string"},
                    "title": {"type": "string", "description": "New title"},
                    "description": {"type": "string"},
                    "status": {"type": "string"},
                    "priority": {"type": "integer"},
                    "assignee_name": {"type": "string", "description": "New assignee name"},
                    "assignee_email": {"type": "string", "description": "New assignee email"},
                    "completed_at": {
                        "type": "string",
                        "description": (
                            "ISO-8601 completion time when the user explicitly gave one. "
                            "Omit to use the Zulip message send time."
                        ),
                    },
                },
                "required": [],
            },
            handler=lambda arguments: _update_todo(workflow, arguments),
        )
    )
    registry.register(
        RegisteredTool(
            name="todo.delete",
            description=(
                "Delete a TraceForge Todo. Locate with match_title / match_assignee_* / topic; "
                "do not ask users for database ids. Soft-deletes the matched record."
            ),
            schema={
                "type": "object",
                "properties": {
                    "todo_id": {
                        "type": "string",
                        "description": "Internal only if already known from a prior tool result _internal_id",
                    },
                    "match_title": {"type": "string"},
                    "match_assignee_name": {"type": "string"},
                    "match_assignee_email": {"type": "string"},
                    "topic": {"type": "string"},
                    "channel_name": {"type": "string"},
                },
                "required": [],
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
    registry.register(
        RegisteredTool(
            name="subtree.children",
            description=(
                "List child org-subtrees under a parent node (or L1 roots if parent omitted). "
                "Use for questions like: 硬件下面有哪些子组织树. "
                "Default lists direct children; set include_descendants=true for full subtree."
            ),
            schema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "subtree_id": {"type": "string"},
                    "subtree_code": {"type": "string"},
                    "subtree_name": {"type": "string"},
                    "subtree_path": {"type": "string"},
                    "include_descendants": {
                        "type": "boolean",
                        "description": "false=direct children only (default); true=all descendants",
                    },
                },
                "required": ["workspace_id"],
            },
            handler=lambda arguments: _subtree_children(workflow, arguments),
        )
    )
    registry.register(
        RegisteredTool(
            name="subtree.todos",
            description=(
                "List Todos hanging on a subtree. Stream/Topic chat defaults to current Topic; "
                "private chat is unrestricted unless topic is provided. "
                "Descendants included by default."
            ),
            schema={
                "type": "object",
                "properties": {
                    "workspace_id": {"type": "string"},
                    "subtree_id": {"type": "string"},
                    "subtree_code": {"type": "string"},
                    "subtree_name": {"type": "string"},
                    "subtree_path": {"type": "string"},
                    "topic": {"type": "string"},
                    "status": {"type": "string"},
                    "include_descendants": {"type": "boolean"},
                    "include_description": {"type": "boolean"},
                },
                "required": ["workspace_id"],
                "anyOf": [
                    {"required": ["subtree_name"]},
                    {"required": ["subtree_code"]},
                    {"required": ["subtree_path"]},
                    {"required": ["subtree_id"]},
                ],
            },
            handler=lambda arguments: _subtree_todos(workflow, arguments),
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
        subtree_id=arguments.get("subtree_id"),
        subtree_code=arguments.get("subtree_code"),
        subtree_name=arguments.get("subtree_name"),
        subtree_path=arguments.get("subtree_path"),
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
    priority_raw = arguments.get("priority")
    include_description = _parse_bool(arguments.get("include_description"))
    command = TodoCommand(
        action=TodoAction.LIST,
        raw_text=str(arguments),
        status=status,
        assignee_email=arguments.get("assignee_email"),
        assignee_name=arguments.get("assignee_name"),
        proposer_email=arguments.get("proposer_email"),
        proposer_name=arguments.get("proposer_name"),
        topic=arguments.get("topic"),
        channel_name=arguments.get("channel_name"),
        priority=int(priority_raw) if priority_raw is not None else 0,
        title_contains=arguments.get("title_contains"),
        group_by=arguments.get("group_by"),
        include_description=include_description,
        subtree_code=arguments.get("subtree_code"),
        subtree_name=arguments.get("subtree_name"),
        subtree_path=arguments.get("subtree_path"),
        include_descendants=_parse_bool(arguments.get("include_descendants"), default=True),
    )
    result = workflow.handle(event, command)
    return ToolResult(
        tool_name="todo.list",
        ok=True,
        data={
            "reply_text": result.reply_text,
            "todos": [item.to_dict() for item in result.todos],
            "display_mode": next(
                (
                    evidence.get("mode")
                    for evidence in result.evidence
                    if isinstance(evidence, dict) and evidence.get("type") == "todo.list"
                ),
                None,
            ),
        },
        evidence=result.evidence,
    )


def _update_todo(workflow: TodoWorkflow, arguments: dict[str, Any]) -> ToolResult:
    event = _event_from_tool(arguments)
    command = TodoCommand(
        action=TodoAction.UPDATE,
        raw_text=str(arguments.get("raw_text") or arguments),
        todo_id=str(arguments.get("todo_id") or "") or None,
        match_title=arguments.get("match_title"),
        match_assignee_name=arguments.get("match_assignee_name"),
        match_assignee_email=arguments.get("match_assignee_email"),
        title=arguments.get("title"),
        description=arguments.get("description"),
        status=_parse_status(arguments.get("status")),
        priority=int(arguments["priority"]) if arguments.get("priority") is not None else 0,
        assignee_name=arguments.get("assignee_name"),
        assignee_email=arguments.get("assignee_email"),
        topic=arguments.get("topic"),
        channel_name=arguments.get("channel_name"),
        completed_at=_parse_optional_time(arguments.get("completed_at")),
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
        raw_text=str(arguments.get("raw_text") or arguments),
        todo_id=str(arguments.get("todo_id") or "") or None,
        match_title=arguments.get("match_title"),
        match_assignee_name=arguments.get("match_assignee_name"),
        match_assignee_email=arguments.get("match_assignee_email"),
        topic=arguments.get("topic"),
        channel_name=arguments.get("channel_name"),
        title_contains=arguments.get("match_title"),
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
    message_type = arguments.get("message_type")
    raw = arguments.get("raw")
    payload: dict[str, Any] = {
        "text": str(
            arguments.get("raw_text")
            or arguments.get("description")
            or arguments.get("title")
            or ""
        ),
    }
    if message_type:
        payload["message_type"] = message_type
    if isinstance(raw, dict):
        payload["raw"] = raw
    return WorkspaceEvent(
        source=_source_from(arguments),
        kind=_kind_from(arguments),
        actor=_actor_from(arguments),
        location=_location_from(arguments, workspace_id=workspace_id, channel_name=channel_name, topic=topic),
        payload=payload,
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


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "是"}


def _parse_time(value: Any) -> datetime:
    parsed = _parse_optional_time(value)
    return parsed if parsed is not None else datetime.now(timezone.utc)


def _parse_optional_time(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        text = str(value).strip()
        if text.isdigit():
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _subtree_children(workflow: TodoWorkflow, arguments: dict[str, Any]) -> ToolResult:
    event = _event_from_tool(arguments)
    command = TodoCommand(
        action=TodoAction.SUBTREE_CHILDREN,
        raw_text=str(arguments),
        subtree_id=arguments.get("subtree_id"),
        subtree_code=arguments.get("subtree_code"),
        subtree_name=arguments.get("subtree_name"),
        subtree_path=arguments.get("subtree_path"),
        include_descendants=_parse_bool(arguments.get("include_descendants"), default=False),
    )
    result = workflow.handle(event, command)
    return ToolResult(
        tool_name="subtree.children",
        ok=True,
        data={"reply_text": result.reply_text},
        evidence=result.evidence,
    )


def _subtree_todos(workflow: TodoWorkflow, arguments: dict[str, Any]) -> ToolResult:
    event = _event_from_tool(arguments)
    command = TodoCommand(
        action=TodoAction.SUBTREE_TODOS,
        raw_text=str(arguments),
        subtree_id=arguments.get("subtree_id"),
        subtree_code=arguments.get("subtree_code"),
        subtree_name=arguments.get("subtree_name"),
        subtree_path=arguments.get("subtree_path"),
        topic=arguments.get("topic"),
        status=_parse_status(arguments.get("status")),
        include_descendants=_parse_bool(arguments.get("include_descendants"), default=True),
        include_description=_parse_bool(arguments.get("include_description"), default=False),
    )
    result = workflow.handle(event, command)
    return ToolResult(
        tool_name="subtree.todos",
        ok=True,
        data={
            "reply_text": result.reply_text,
            "todos": [item.to_dict() for item in result.todos],
        },
        evidence=result.evidence,
    )

