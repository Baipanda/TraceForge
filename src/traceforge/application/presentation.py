"""Canonical Zulip reply templates for TraceForge.

All user-visible success/list panels (Todo, Subtree, and future domains) are
composed here so AgentRuntime can force-pass ``reply_text`` without LLM rewrite.
Keep database IDs out of replies. Cap detail lists for Zulip length limits.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from typing import Iterable
from zoneinfo import ZoneInfo

from traceforge.core.subtrees import SubtreeRecord
from traceforge.core.todos import TodoRecord

ZULIP_SAFE_CHARS = 3500
MAX_DETAIL_ITEMS = 8


def _display_tz() -> ZoneInfo:
    name = (os.environ.get("TRACEFORGE_DISPLAY_TZ") or "Asia/Shanghai").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    local = value.astimezone(_display_tz())
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _cell(value: object) -> str:
    text = "—" if value is None else str(value)
    text = text.replace("\n", " ").replace("|", "/")
    return text.strip() or "—"


def _markdown_table(
    *,
    title: str,
    headers: list[str],
    rows: list[list[str]],
    count_label: str | None = None,
) -> str:
    """Shared Markdown table shell used by Todo and Subtree panels."""
    lines = [title]
    if count_label:
        lines.append(count_label)
    lines.extend(
        [
            "",
            "| " + " | ".join(headers) + " |",
            "|" + "|".join(["---"] * len(headers)) + "|",
        ]
    )
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def format_todo_item(todo: TodoRecord, *, index: int | None = None, include_description: bool = False) -> str:
    """Legacy card format. Prefer table panels for user replies."""
    prefix = f"{index}. " if index is not None else ""
    assignee = todo.assignee_name or todo.assignee_email or "未指定"
    proposer = todo.proposer_name or todo.proposer_email or "未指定"
    topic = todo.topic or "—"
    channel = todo.channel_name or "—"
    subtree = todo.subtree_label or todo.subtree_id or "—"
    lines = [
        f"**{prefix}{todo.title}**",
        f"- 状态：{todo.status.value}",
        f"- 执行者：{assignee}",
        f"- 发布者：{proposer}",
        f"- 组织树：{subtree}",
        f"- 频道：{channel}",
        f"- Topic：{topic}",
        f"- 优先级：{todo.priority}",
        f"- 发布时间：{format_datetime(todo.created_at)}",
        f"- 完成时间：{format_datetime(todo.completed_at)}",
    ]
    if include_description and todo.description:
        lines.append(f"- 描述：{todo.description}")
    return "\n".join(lines)


def format_filter_line(filters: dict[str, object]) -> str:
    parts: list[str] = []
    labels = (
        ("topic", "Topic"),
        ("assignee_email", "执行者邮箱"),
        ("assignee_name", "执行者"),
        ("status", "状态"),
        ("channel_name", "频道"),
        ("proposer_email", "发布者邮箱"),
        ("priority", "优先级"),
        ("title_contains", "标题包含"),
        ("subtree", "组织树"),
    )
    for key, label in labels:
        value = filters.get(key)
        if value is None or value == "":
            continue
        parts.append(f"{label}={value}")
    return "、".join(parts) if parts else "无额外过滤"


def format_group_summary(
    todos: list[TodoRecord],
    *,
    total: int,
    filters: dict[str, object],
    preferred_group: str | None = None,
) -> str:
    by_topic = Counter((todo.topic or "（无 Topic）") for todo in todos)
    by_assignee = Counter(
        (todo.assignee_name or todo.assignee_email or "未指定") for todo in todos
    )
    by_status = Counter(todo.status.value for todo in todos)

    lines = [
        f"共找到 **{total}** 条 Todo，数量较多，为避免超出 Zulip 消息长度，先做汇总。",
        "",
        "### 按 Topic",
    ]
    for name, count in by_topic.most_common():
        lines.append(f"- {name}：{count}")
    lines.extend(["", "### 按执行者"])
    for name, count in by_assignee.most_common():
        lines.append(f"- {name}：{count}")
    lines.extend(["", "### 按状态"])
    for name, count in by_status.most_common():
        lines.append(f"- {name}：{count}")

    hint_group = preferred_group or "topic"
    if hint_group == "assignee":
        example = "「查看 Peter 的 Todo」或「Neymar 未完成的 Todo」"
    else:
        example = "「查看 football 下的 Todo」或「agent开发 里 Gwen 的 Todo」"
    lines.extend(
        [
            "",
            "请继续缩小范围后再查，例如：",
            f"- {example}",
            "- 「只要 open / in_progress / done」",
        ]
    )
    return "\n".join(lines)


def should_summarize(todos: list[TodoRecord], *, include_description: bool = False) -> bool:
    if len(todos) > MAX_DETAIL_ITEMS:
        return True
    preview = format_todo_list_detail(
        todos, filters={}, header="预览", include_description=include_description
    )
    return len(preview) > ZULIP_SAFE_CHARS


def format_todo_list_detail(
    todos: Iterable[TodoRecord],
    *,
    filters: dict[str, object],
    header: str,
    max_items: int = MAX_DETAIL_ITEMS,
    include_description: bool = False,
) -> str:
    items = list(todos)
    shown = items[:max_items]
    headers = [
        "标题",
        "状态",
        "执行者",
        "发布者",
        "组织树",
        "Topic",
        "优先级",
        "发布时间",
        "完成时间",
    ]
    if include_description:
        headers.append("描述")
    rows: list[list[str]] = []
    for todo in shown:
        cells = [
            _cell(todo.title),
            _cell(todo.status.value),
            _cell(todo.assignee_name or todo.assignee_email),
            _cell(todo.proposer_name or todo.proposer_email),
            _cell(todo.subtree_label or todo.subtree_id),
            _cell(todo.topic),
            _cell(todo.priority),
            _cell(format_datetime(todo.created_at)),
            _cell(format_datetime(todo.completed_at)),
        ]
        if include_description:
            cells.append(_cell(todo.description))
        rows.append(cells)
    count_label = f"共 {len(items)} 条" + (
        f"（展示前 {len(shown)} 条）" if len(items) > len(shown) else ""
    )
    body = _markdown_table(title=header, headers=headers, rows=rows, count_label=count_label)
    if len(items) > len(shown):
        body += f"\n\n还有 {len(items) - len(shown)} 条未展开。请按 Topic / 执行者 / 状态继续筛选。"
    return body


def format_todo_list_reply(
    todos: list[TodoRecord],
    *,
    filters: dict[str, object],
    scope_label: str,
    force_group: str | None = None,
    include_description: bool = False,
) -> tuple[str, str]:
    if not todos:
        return f"当前条件下没有找到 Todo。（查询范围：{scope_label}）", "empty"

    if force_group in {"topic", "assignee", "status"} or should_summarize(
        todos, include_description=include_description
    ):
        return (
            format_group_summary(
                todos,
                total=len(todos),
                filters=filters,
                preferred_group=force_group if force_group in {"topic", "assignee"} else "topic",
            ),
            "summary",
        )

    header = f"Todo 列表（{scope_label}）"
    return (
        format_todo_list_detail(
            todos,
            filters=filters,
            header=header,
            include_description=include_description,
        ),
        "detail",
    )


def format_todo_create_reply(todo: TodoRecord) -> str:
    return format_todo_list_detail([todo], filters={}, header="已创建 Todo", max_items=1)


def format_todo_update_reply(todo: TodoRecord, *, changed: dict[str, object] | None = None) -> str:
    body = format_todo_list_detail([todo], filters={}, header="已更新 Todo", max_items=1)
    if not changed:
        return body
    change_bits = [f"{key} → {value}" for key, value in changed.items() if value is not None]
    if not change_bits:
        return body
    return body + "\n\n变更：" + "；".join(change_bits)


def format_todo_delete_reply(todo: TodoRecord) -> str:
    return format_todo_list_detail([todo], filters={}, header="已删除 Todo", max_items=1)


def format_subtree_path_label(node: SubtreeRecord, labels: dict[str, str] | None = None) -> str:
    if labels and node.id in labels:
        return labels[node.id]
    return node.name


def format_subtree_children_reply(
    parent: SubtreeRecord | None,
    children: list[SubtreeRecord],
    *,
    labels: dict[str, str] | None = None,
    recursive: bool = False,
) -> str:
    if parent is None:
        scope = "组织树根节点（L1）"
    else:
        scope = f"组织树 `{format_subtree_path_label(parent, labels)}`"
    mode = "全部子孙" if recursive else "直接子节点"
    header = f"Subtree 列表（{scope} / {mode}）"
    if not children:
        return f"{header}\n\n当前没有子节点。"
    rows = [
        [
            _cell(node.name),
            _cell(node.level),
            _cell(node.code),
            _cell(format_subtree_path_label(node, labels)),
        ]
        for node in children
    ]
    return _markdown_table(
        title=header,
        headers=["名称", "级别", "Code", "路径"],
        rows=rows,
        count_label=f"共 {len(children)} 个",
    )


def public_todo_dict(todo: TodoRecord) -> dict[str, object]:
    data = todo.to_dict()
    internal_id = data.pop("id")
    data["_internal_id"] = internal_id
    return data
