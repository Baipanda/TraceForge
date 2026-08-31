from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import uuid4

from traceforge.core.events import WorkspaceEvent
from traceforge.infrastructure.identity.person_store import PersonStore
from traceforge.core.todos import TodoAction, TodoCommand, TodoFilter, TodoRecord, TodoStatus
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository
from traceforge.application.presentation import (
    format_todo_create_reply,
    format_todo_delete_reply,
    format_todo_list_reply,
    format_todo_update_reply,
    format_todo_list_detail,
    format_subtree_children_reply,
    format_subtree_path_label,
    public_todo_dict,
)


@dataclass(frozen=True)
class TodoWorkflowResult:
    action: TodoAction
    reply_text: str
    evidence: list[dict[str, object]] = field(default_factory=list)
    todo: TodoRecord | None = None
    todos: list[TodoRecord] = field(default_factory=list)


class TodoWorkflow:
    def __init__(self, repository: SqliteTodoRepository, person_store: PersonStore | None = None) -> None:
        self.repository = repository
        self.person_store = person_store or PersonStore(repository.db_path)

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
        if command.action == TodoAction.SUBTREE_CHILDREN:
            return self._subtree_children(event, command)
        if command.action == TodoAction.SUBTREE_TODOS:
            return self._subtree_todos(event, command)
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
        topic = command.topic or event.location.topic
        subtree = self.repository.resolve_subtree_for_create(
            event.location.workspace_id,
            subtree_id=command.subtree_id,
            subtree_code=command.subtree_code,
            subtree_name=command.subtree_name,
            subtree_path=command.subtree_path,
            topic=topic,
            create_missing=True,
        )
        if subtree is None:
            return TodoWorkflowResult(
                action=TodoAction.CREATE,
                reply_text=(
                    "创建 Todo 需要指定组织树（subtree）。可传："
                    "`subtree_path=硬件/主控板/EMI测试`（按名称路径，缺失的 L2/L3 会自动创建）、"
                    "`subtree_code=software.cloud.agent`，或在已知 Topic 下自动匹配。"
                ),
                evidence=[{"type": "todo.create", "status": "missing_subtree"}],
            )
        todo = TodoRecord(
            id=f"todo_{uuid4().hex[:8]}",
            title=title,
            description=command.description,
            status=command.status or TodoStatus.OPEN,
            priority=command.priority,
            workspace_id=event.location.workspace_id,
            subtree_id=subtree.id,
            channel_name=event.location.channel_name,
            topic=topic,
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
            reply_text=format_todo_create_reply(record),
            evidence=[{"type": "todo.create", "todo": public_todo_dict(record)}],
            todo=record,
        )

    def _list(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        private = _is_private_conversation(event)
        # Private chat: do NOT default to a Topic, but honor an explicit topic filter.
        # Stream/Topic chat: default to the current Topic when the user did not override it.
        topic = _resolve_list_topic(event, command, private=private)
        include_description = bool(command.include_description)
        filters = {
            "topic": topic,
            "assignee_email": command.assignee_email,
            "assignee_name": command.assignee_name,
            "proposer_email": command.proposer_email,
            "proposer_name": command.proposer_name,
            "status": command.status.value if command.status else None,
            "channel_name": command.channel_name,
            "priority": command.priority if command.priority else None,
            "title_contains": command.title_contains or command.match_title,
            "include_description": include_description or None,
        }
        subtree_id = None
        subtree_path_prefix = None
        if command.subtree_id or command.subtree_code or command.subtree_name or command.subtree_path:
            node = self.repository.resolve_subtree_for_create(
                event.location.workspace_id,
                subtree_id=command.subtree_id,
                subtree_code=command.subtree_code,
                subtree_name=command.subtree_name,
                subtree_path=command.subtree_path,
                create_missing=False,
            )
            if node is None:
                return TodoWorkflowResult(
                    action=TodoAction.LIST,
                    reply_text="没有找到对应的组织树节点，请检查 subtree_path / subtree_code / 名称。",
                    evidence=[{"type": "todo.list", "status": "subtree_not_found"}],
                )
            if command.include_descendants:
                subtree_path_prefix = node.path
            else:
                subtree_id = node.id

        # Private chat drops workspace scoping for broad todo search, but subtree
        # nodes are always resolved inside the current workspace.
        filter_workspace = event.location.workspace_id if (subtree_id or subtree_path_prefix or not private) else None
        todo_filter = TodoFilter(
            workspace_id=filter_workspace,
            status=command.status,
            assignee_email=command.assignee_email,
            assignee_name=command.assignee_name,
            proposer_email=command.proposer_email,
            proposer_name=command.proposer_name,
            topic=topic,
            channel_name=command.channel_name,
            priority=command.priority if command.priority else None,
            title_contains=command.title_contains or command.match_title,
            subtree_id=subtree_id,
            subtree_path_prefix=subtree_path_prefix,
            include_descendants=command.include_descendants,
            include_description=include_description,
            limit=100 if private else 50,
        )
        todos = self.repository.list_todos(todo_filter)
        if private and topic:
            scope = f"私聊 / Topic `{topic}`"
        elif private:
            scope = "私聊（未指定 Topic，不限 Topic）"
        else:
            scope = f"Topic `{topic or 'unknown'}`"
        reply_text, mode = format_todo_list_reply(
            todos,
            filters=filters,
            scope_label=scope,
            force_group=command.group_by,
            include_description=include_description,
        )
        return TodoWorkflowResult(
            action=TodoAction.LIST,
            reply_text=reply_text,
            evidence=[
                {
                    "type": "todo.list",
                    "filters": {k: v for k, v in filters.items() if v is not None},
                    "count": len(todos),
                    "private": private,
                    "mode": mode,
                }
            ],
            todos=todos,
        )

    def _update(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        private = _is_private_conversation(event)
        target, locate_error = self._locate_todo(event, command, private=private)
        if target is None:
            return TodoWorkflowResult(
                action=TodoAction.UPDATE,
                reply_text=locate_error or "无法定位要更新的 Todo，请补充标题、执行者或 Topic。",
                evidence=[{"type": "todo.update", "status": "not_located"}],
            )
        status = command.status
        # Already-done todos used to lock completed_at. If the user is clearly asking
        # to change the completion time but the model only sent match_* fields, re-stamp
        # with this Zulip message time instead of no-oping.
        if (
            status is None
            and command.completed_at is None
            and target.status == TodoStatus.DONE
            and _mentions_completion_time(command.raw_text)
        ):
            status = TodoStatus.DONE
        try:
            record = self.repository.update_todo(
                target.id,
                title=command.title,
                description=command.description,
                status=status,
                priority=command.priority if command.priority else None,
                assignee_name=command.assignee_name,
                assignee_email=command.assignee_email,
                event=event,
                extra={"raw_text": command.raw_text},
                at=event.occurred_at,
                completed_at=command.completed_at,
                completed_at_provided=command.completed_at is not None,
            )
        except KeyError:
            return TodoWorkflowResult(
                action=TodoAction.UPDATE,
                reply_text="没有找到要更新的 Todo，请换一组更具体的条件再试。",
                evidence=[{"type": "todo.update", "status": "not_found"}],
            )
        changed = {
            "title": command.title,
            "status": command.status.value if command.status else None,
            "assignee": command.assignee_name or command.assignee_email,
        }
        if command.completed_at is not None or record.completed_at != target.completed_at:
            changed["completed_at"] = (
                record.completed_at.isoformat() if record.completed_at else None
            )
        return TodoWorkflowResult(
            action=TodoAction.UPDATE,
            reply_text=format_todo_update_reply(record, changed=changed),
            evidence=[{"type": "todo.update", "todo": public_todo_dict(record)}],
            todo=record,
        )

    def _locate_todo(
        self,
        event: WorkspaceEvent,
        command: TodoCommand,
        *,
        private: bool,
        purpose: str = "更新",
    ) -> tuple[TodoRecord | None, str | None]:
        if command.todo_id:
            found = self.repository.get_todo(command.todo_id)
            if found is None:
                return None, "没有找到对应的 Todo，请用标题 + 执行者 / Topic 再定位。"
            return found, None

        topic = _resolve_list_topic(event, command, private=private)
        raw_match_title = command.match_title or command.title_contains
        match_title = _clean_match_title(raw_match_title)
        match_assignee_email = command.match_assignee_email
        match_assignee_name = command.match_assignee_name

        if not match_title and not match_assignee_email and not match_assignee_name and not topic:
            return None, (
                f"{purpose} Todo 请提供定位信息（标题关键词、执行者，或先在当前 Topic 查询后再指定），"
                "不要向用户展示或索要数据库内部 ID。"
            )

        base_filter = TodoFilter(
            workspace_id=None if private else event.location.workspace_id,
            assignee_email=match_assignee_email,
            assignee_name=match_assignee_name if not match_assignee_email else None,
            topic=topic,
            channel_name=command.channel_name,
            limit=50,
        )
        candidates = self.repository.list_todos(
            TodoFilter(
                **{
                    **base_filter.__dict__,
                    "title_contains": match_title,
                    "limit": 20,
                }
            )
        )
        if match_title:
            candidates = _rank_todos_by_title(candidates, match_title)
            if not candidates:
                # Typo / partial title: broaden search then fuzzy-rank.
                broader = self.repository.list_todos(base_filter)
                candidates = _rank_todos_by_title(broader, match_title, min_ratio=0.55)

        if len(candidates) == 1:
            return candidates[0], None
        if not candidates:
            return None, "没有找到匹配的 Todo，请调整标题 / 执行者 / Topic 后再试。"

        preview = format_todo_list_detail(
            candidates[:8],
            filters={
                "topic": topic,
                "assignee_email": match_assignee_email,
                "assignee_name": match_assignee_name,
                "title_contains": match_title,
            },
            header=f"匹配到多条 Todo，请补充条件后再{purpose}：",
        )
        return None, preview

    def _delete(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        private = _is_private_conversation(event)
        target, locate_error = self._locate_todo(
            event,
            command,
            private=private,
            purpose="删除",
        )
        if target is None:
            return TodoWorkflowResult(
                action=TodoAction.DELETE,
                reply_text=locate_error or "无法定位要删除的 Todo，请补充标题、执行者或 Topic。",
                evidence=[{"type": "todo.delete", "status": "not_located"}],
            )
        try:
            record = self.repository.delete_todo(target.id, event=event)
        except KeyError:
            return TodoWorkflowResult(
                action=TodoAction.DELETE,
                reply_text="没有找到要删除的 Todo，请换一组更具体的条件再试。",
                evidence=[{"type": "todo.delete", "status": "not_found"}],
            )
        return TodoWorkflowResult(
            action=TodoAction.DELETE,
            reply_text=format_todo_delete_reply(record),
            evidence=[{"type": "todo.delete", "todo": public_todo_dict(record)}],
            todo=record,
        )

    def _summary(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        private = _is_private_conversation(event)
        topic = _resolve_list_topic(event, command, private=private)
        todo_filter = TodoFilter(
            workspace_id=None if private else event.location.workspace_id,
            status=command.status,
            assignee_email=command.assignee_email,
            topic=topic,
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


    def _subtree_children(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        parent, children = self.repository.list_child_subtrees(
            event.location.workspace_id,
            parent_id=command.subtree_id,
            parent_code=command.subtree_code,
            parent_name=command.subtree_name,
            parent_path=command.subtree_path,
            recursive=bool(command.include_descendants),
        )
        if (command.subtree_id or command.subtree_code or command.subtree_name or command.subtree_path) and parent is None:
            return TodoWorkflowResult(
                action=TodoAction.SUBTREE_CHILDREN,
                reply_text="没有找到对应的组织树节点，请检查名称 / code / path。",
                evidence=[{"type": "subtree.children", "status": "not_found"}],
            )
        labels = {}
        # Prefer repository label map via attached path labels on demand
        for node in ([parent] if parent else []) + children:
            if node is not None:
                label = self.repository.subtree_label(node.id)
                if label:
                    labels[node.id] = label
        reply = format_subtree_children_reply(
            parent,
            children,
            labels=labels,
            recursive=bool(command.include_descendants),
        )
        return TodoWorkflowResult(
            action=TodoAction.SUBTREE_CHILDREN,
            reply_text=reply,
            evidence=[
                {
                    "type": "subtree.children",
                    "parent": parent.code if parent else None,
                    "count": len(children),
                    "recursive": bool(command.include_descendants),
                }
            ],
        )

    def _subtree_todos(self, event: WorkspaceEvent, command: TodoCommand) -> TodoWorkflowResult:
        # Reuse list scoping rules, but require a subtree anchor.
        if not (command.subtree_id or command.subtree_code or command.subtree_name or command.subtree_path):
            return TodoWorkflowResult(
                action=TodoAction.SUBTREE_TODOS,
                reply_text="请指定组织树节点，例如：`硬件` 或 `subtree_path=软件/云边协同`。",
                evidence=[{"type": "subtree.todos", "status": "missing_subtree"}],
            )
        # Force include_descendants default True for this action unless explicitly false...
        # TodoCommand defaults include_descendants=True.
        list_command = TodoCommand(
            action=TodoAction.LIST,
            raw_text=command.raw_text,
            status=command.status,
            assignee_email=command.assignee_email,
            assignee_name=command.assignee_name,
            topic=command.topic,
            channel_name=command.channel_name,
            title_contains=command.title_contains,
            subtree_id=command.subtree_id,
            subtree_code=command.subtree_code,
            subtree_name=command.subtree_name,
            subtree_path=command.subtree_path,
            include_descendants=command.include_descendants,
            include_description=command.include_description,
            group_by=command.group_by,
        )
        result = self._list(event, list_command)
        return TodoWorkflowResult(
            action=TodoAction.SUBTREE_TODOS,
            reply_text=result.reply_text,
            evidence=[{"type": "subtree.todos", **(result.evidence[0] if result.evidence else {})}],
            todos=result.todos,
        )

    def _resolve_assignee(self, command: TodoCommand) -> tuple[str | None, str | None]:
        if command.assignee_email:
            person = self.person_store.resolve(command.assignee_email)
            if person is not None:
                return person.display_name, person.primary_email
            return command.assignee_name, command.assignee_email
        if command.assignee_name:
            person = self.person_store.resolve(command.assignee_name)
            if person is not None:
                return person.display_name, person.primary_email
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


def _resolve_list_topic(
    event: WorkspaceEvent,
    command: TodoCommand,
    *,
    private: bool,
) -> str | None:
    """Resolve Topic filter for list/update/summary.

    - Private chat: no implicit Topic; only use an explicit ``command.topic``.
    - Stream/Topic chat: use explicit topic, otherwise the current message Topic.
    """
    explicit = (command.topic or "").strip() or None
    if private:
        return explicit
    return explicit or event.location.topic


def _clean_match_title(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    for prefix in ("我的todo：", "我的todo:", "我的 Todo：", "我的 Todo:", "todo：", "todo:", "Todo：", "Todo:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix) :].strip()
    for noise in (
        "已经完成了，更新状态",
        "已经完成了",
        "已完成，更新状态",
        "已完成",
        "更新状态",
        "请更新状态",
        "帮我更新",
    ):
        text = text.replace(noise, "")
    text = text.strip(" ：:，,。；;.")
    return text or None


def _rank_todos_by_title(
    todos: list[TodoRecord],
    match_title: str,
    *,
    min_ratio: float = 0.72,
) -> list[TodoRecord]:
    from difflib import SequenceMatcher

    needle = match_title.strip().lower()
    if not needle:
        return list(todos)

    exact = [todo for todo in todos if todo.title == match_title]
    if exact:
        return exact

    contains = [
        todo
        for todo in todos
        if needle in todo.title.lower() or todo.title.lower() in needle
    ]
    if len(contains) == 1:
        return contains
    if contains:
        return contains

    scored: list[tuple[float, TodoRecord]] = []
    for todo in todos:
        ratio = SequenceMatcher(None, needle, todo.title.lower()).ratio()
        # Also reward long shared substrings (helps 攥写 vs 撰写).
        shared = _longest_shared_run(needle, todo.title.lower())
        if shared >= 6:
            ratio = max(ratio, 0.6 + min(shared, 20) / 50)
        if ratio >= min_ratio:
            scored.append((ratio, todo))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return []
    best = scored[0][0]
    # Keep only near-best matches to avoid ambiguous updates.
    return [todo for ratio, todo in scored if best - ratio <= 0.08]


def _longest_shared_run(left: str, right: str) -> int:
    best = 0
    for i in range(len(left)):
        for j in range(i + 1, len(left) + 1):
            chunk = left[i:j]
            if len(chunk) > best and chunk in right:
                best = len(chunk)
    return best


def _is_private_conversation(event: WorkspaceEvent) -> bool:
    """Detect Zulip DM / private message conversations."""
    payload = event.payload or {}
    message_type = str(payload.get("message_type") or "").strip().lower()
    if message_type == "private":
        return True
    raw = payload.get("raw")
    if isinstance(raw, dict):
        message = raw.get("message") if isinstance(raw.get("message"), dict) else raw
        if isinstance(message, dict) and str(message.get("type") or "").lower() == "private":
            return True
    return False


def _mentions_completion_time(text: str | None) -> bool:
    """Heuristic: user is asking to change completion time, not just status."""
    if not text:
        return False
    lowered = text.casefold()
    tokens = (
        "完成时间",
        "完成时间为",
        "完成时间改",
        "完成时间更新",
        "改一下完成时间",
        "更新完成时间",
        "completed_at",
        "completion time",
        "complete time",
    )
    return any(token.casefold() in lowered for token in tokens)


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
    match = re.search(r"给\s*(.+?)(?:发布|创建)", text)
    if not match:
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
