from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import uuid4

from traceforge.core.events import WorkspaceEvent
from traceforge.infrastructure.identity.people_directory import PeopleDirectory
from traceforge.core.todos import TodoAction, TodoCommand, TodoFilter, TodoRecord, TodoStatus
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository


@dataclass(frozen=True)
class TodoWorkflowResult:
    action: TodoAction
    reply_text: str
    evidence: list[dict[str, object]] = field(default_factory=list)
    todo: TodoRecord | None = None
    todos: list[TodoRecord] = field(default_factory=list)


class TodoWorkflow:
    def __init__(self, repository: SqliteTodoRepository, people_directory: PeopleDirectory | None = None) -> None:
        self.repository = repository
        self.people_directory = people_directory or PeopleDirectory()

    def handle(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        if command.action == TodoAction.CREATE:
            return self._create(event, command)
        if command.action == TodoAction.LIST:
            return self._list(event, command)
        if command.action == TodoAction.UPDATE:
            return self._update(event, command)
        if command.action == TodoAction.DELETE:
            return self._delete(event, command)
        if command.action == TodoAction.SUMMARY:
            return self._summary(event, command)
        return TodoWorkflowResult(
            action=TodoAction.UNKNOWN,
            reply_text="我识别到了一个待办相关请求，但还没法确定你要创建、查询、更新、删除还是总结。",
            evidence=[{"type": "todo.intent", "action": TodoAction.UNKNOWN.value}],
        )

    def _create(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        title = (command.title or command.raw_text.strip()).strip()
        if not title:
            return TodoWorkflowResult(
                action=TodoAction.CREATE,
                reply_text="创建 Todo 需要一个明确的标题，例如：`给 Neymar 发布一个 todo：检查认证模块 SQL 注入风险`。",
                evidence=[{"type": "todo.create", "status": "missing_title"}],
            )
        if not (event.actor.display_name or event.actor.email):
            return TodoWorkflowResult(
                action=TodoAction.CREATE,
                reply_text="创建 Todo 需要能识别发布者。当前消息缺少 Zulip 用户名称或邮箱。",
                evidence=[{"type": "todo.create", "status": "missing_proposer"}],
            )
        assignee = self._resolve_assignee(command)
        if not (assignee[0] or assignee[1]):
            return TodoWorkflowResult(
                action=TodoAction.CREATE,
                reply_text="创建 Todo 需要指定执行者，例如：`给 Neymar 发布一个 todo：检查认证模块 SQL 注入风险`。",
                evidence=[{"type": "todo.create", "status": "missing_assignee"}],
            )
        todo = TodoRecord(
            id=f"todo_{uuid4().hex[:8]}",
            title=title,
            description=command.description or command.raw_text,
            status=command.status or TodoStatus.OPEN,
            priority=command.priority,
            workspace_id=event.location.workspace_id,
            channel_name=event.location.channel_name,
            topic=command.topic or event.location.topic,
            proposer_name=event.actor.display_name,
            proposer_email=event.actor.email,
            assignee_name=assignee[0],
            assignee_email=assignee[1],
            source_message_id=event.external_event_id,
            created_at=event.occurred_at,
            updated_at=event.occurred_at,
        )
        record = self.repository.create_todo(todo, event=event)
        return TodoWorkflowResult(
            action=TodoAction.CREATE,
            reply_text=(
                f"已创建 Todo：`{record.id}`\n"
                f"- 标题：{record.title}\n"
                f"- 发布者：{record.proposer_name or record.proposer_email or 'unknown'}\n"
                f"- 执行者：{record.assignee_name or record.assignee_email or 'unknown'}\n"
                f"- 状态：{record.status.value}\n"
                f"- 频道：{record.channel_name or 'unknown'} / {record.topic or 'none'}"
            ),
            evidence=[{"type": "todo.create", "todo": record.to_dict()}],
            todo=record,
        )

    def _list(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        todo_filter = TodoFilter(
            workspace_id=event.location.workspace_id,
            status=command.status,
            assignee_email=command.assignee_email,
            topic=command.topic or event.location.topic,
            limit=10,
        )
        todos = self.repository.list_todos(todo_filter)
        if not todos:
            return TodoWorkflowResult(
                action=TodoAction.LIST,
                reply_text="当前条件下没有找到 Todo。",
                evidence=[{"type": "todo.list", "filters": todo_filter.__dict__, "count": 0}],
                todos=[],
            )
        lines = [
            f"- `{todo.id}` {todo.title} [{todo.status.value}]"
            for todo in todos[:5]
        ]
        return TodoWorkflowResult(
            action=TodoAction.LIST,
            reply_text="当前 Todo 列表：\n" + "\n".join(lines),
            evidence=[
                {
                    "type": "todo.list",
                    "filters": todo_filter.__dict__,
                    "count": len(todos),
                }
            ],
            todos=todos,
        )

    def _update(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        if not command.todo_id:
            return TodoWorkflowResult(
                action=TodoAction.UPDATE,
                reply_text="更新 Todo 需要一个明确的 Todo ID，例如 `todo_1234abcd`。",
                evidence=[{"type": "todo.update", "status": "missing_id"}],
            )
        try:
            record = self.repository.update_todo(
                command.todo_id,
                title=command.title,
                description=command.description,
                status=command.status,
                priority=command.priority if command.priority else None,
                assignee_name=command.assignee_name,
                assignee_email=command.assignee_email,
                event=event,
                extra={"raw_text": command.raw_text},
            )
        except KeyError:
            return TodoWorkflowResult(
                action=TodoAction.UPDATE,
                reply_text=f"没有找到 Todo `{command.todo_id}`。",
                evidence=[{"type": "todo.update", "todo_id": command.todo_id, "status": "not_found"}],
            )
        return TodoWorkflowResult(
            action=TodoAction.UPDATE,
            reply_text=(
                f"已更新 Todo `{record.id}`\n"
                f"- 标题：{record.title}\n"
                f"- 状态：{record.status.value}\n"
                f"- 负责人：{record.assignee_name or record.assignee_email or '未指定'}"
            ),
            evidence=[{"type": "todo.update", "todo": record.to_dict()}],
            todo=record,
        )

    def _delete(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        if not command.todo_id:
            return TodoWorkflowResult(
                action=TodoAction.DELETE,
                reply_text="删除 Todo 需要一个明确的 Todo ID，例如 `todo_1234abcd`。",
                evidence=[{"type": "todo.delete", "status": "missing_id"}],
            )
        try:
            record = self.repository.delete_todo(command.todo_id, event=event)
        except KeyError:
            return TodoWorkflowResult(
                action=TodoAction.DELETE,
                reply_text=f"没有找到 Todo `{command.todo_id}`。",
                evidence=[{"type": "todo.delete", "todo_id": command.todo_id, "status": "not_found"}],
            )
        return TodoWorkflowResult(
            action=TodoAction.DELETE,
            reply_text=f"已删除 Todo `{record.id}`：{record.title}",
            evidence=[{"type": "todo.delete", "todo": record.to_dict()}],
            todo=record,
        )

    def _summary(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        todo_filter = TodoFilter(
            workspace_id=event.location.workspace_id,
            status=command.status,
            assignee_email=command.assignee_email,
            topic=command.topic or event.location.topic,
            limit=100,
        )
        summary = self.repository.summarize_todos(todo_filter)
        status_lines = [
            f"- {status}: {count}"
            for status, count in sorted(summary["by_status"].items())
        ]
        return TodoWorkflowResult(
            action=TodoAction.SUMMARY,
            reply_text=(
                f"Todo Summary\n"
                f"- 总数：{summary['total']}\n"
                + "\n".join(status_lines or ["- 暂无条目"])
            ),
            evidence=[{"type": "todo.summary", "summary": summary}],
            todos=[item for item in self.repository.list_todos(todo_filter)],
        )

    def _resolve_assignee(self, command: TodoCommand) -> tuple[str | None, str | None]:
        if command.assignee_email:
            person = self.people_directory.resolve(command.assignee_email)
            if person is not None:
                return person.canonical_name, person.email
            return command.assignee_name, command.assignee_email
        if command.assignee_name:
            person = self.people_directory.resolve(command.assignee_name)
            if person is not None:
                return person.canonical_name, person.email
        return command.assignee_name, command.assignee_email


def parse_todo_command(text: str) -> TodoCommand:
    raw = text.strip()
    lowered = raw.lower()
    action = _detect_action(lowered)
    todo_id = _extract_todo_id(raw)
    status = _extract_status(lowered)
    assignee_name, assignee_email = _extract_assignee(raw)
    topic = _extract_topic(raw)
    title = _extract_title(raw, action)
    return TodoCommand(
        action=action,
        raw_text=raw,
        title=title,
        description=raw if action == TodoAction.CREATE else None,
        todo_id=todo_id,
        assignee_name=assignee_name,
        assignee_email=assignee_email,
        status=status,
        topic=topic,
        query_text=raw,
    )


def _detect_action(lowered: str) -> TodoAction:
    if any(token in lowered for token in ("总结", "summary", "归纳", "汇总")):
        return TodoAction.SUMMARY
    if any(token in lowered for token in ("删除", "移除", "取消", "delete", "remove")):
        return TodoAction.DELETE
    if any(token in lowered for token in ("更新", "修改", "改为", "完成", "标记", "update", "change")):
        return TodoAction.UPDATE
    if any(token in lowered for token in ("查询", "查看", "列出", "list", "展示", "有哪些", "看看")):
        return TodoAction.LIST
    if any(token in lowered for token in ("todo", "待办", "任务", "发布", "创建", "新增", "记录", "安排")):
        return TodoAction.CREATE
    return TodoAction.UNKNOWN


def _extract_todo_id(text: str) -> str | None:
    match = re.search(r"(todo[_-]?[0-9a-fA-F]{6,}|#\d+|\b\d{4,}\b)", text)
    if not match:
        return None
    return match.group(1).lstrip("#")


def _extract_status(lowered: str) -> TodoStatus | None:
    if any(token in lowered for token in ("完成", "done", "finished", "closed")):
        return TodoStatus.DONE
    if any(token in lowered for token in ("进行中", "in progress", "progress")):
        return TodoStatus.IN_PROGRESS
    if any(token in lowered for token in ("取消", "撤销", "canceled")):
        return TodoStatus.CANCELED
    return None


def _extract_assignee(text: str) -> tuple[str | None, str | None]:
    match = re.search(r"给\s*([^\s，。:：]+)", text)
    if not match:
        return None, None
    name = match.group(1).strip()
    if "@" in name:
        return None, name
    return name, None


def _extract_topic(text: str) -> str | None:
    return None


def _extract_title(text: str, action: TodoAction) -> str | None:
    if action != TodoAction.CREATE:
        return None
    cleaned = re.sub(r"^@\S+\s*", "", text).strip()
    if "：" in cleaned:
        cleaned = cleaned.split("：", 1)[1].strip()
    elif ":" in cleaned:
        cleaned = cleaned.split(":", 1)[1].strip()
    for marker in ("发布者是", "执行人是", "负责人是", "执行者是", "发起人是"):
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[0].strip(" ，。:：")
    cleaned = re.sub(
        r"^(请|帮我|麻烦)?(给[^\s，。:：]+)?\s*(创建|新增|发布|记录|安排)?\s*(一个|个)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"(@\*\*[^*]+\*\*|@\S+)$", "", cleaned).strip(" ，。:：")
    return cleaned or text
