from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import replace
from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Any

from traceforge.application.todo_workflow import TodoWorkflow, parse_todo_command
from traceforge.config import get_settings
from traceforge.core.events import WorkspaceEvent
from traceforge.core.todos import TodoAction
from traceforge.infrastructure.identity.person_store import PersonStore
from traceforge.infrastructure.llm.deepseek import DeepSeekClient
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository
from traceforge.memory.markdown_index import MarkdownMemoryIndex
from traceforge.memory.factory import build_markdown_memory_index
from traceforge.memory.markdown_store import MarkdownMemoryStore
from traceforge.tools.models import ToolCall, ToolResult
from traceforge.tools.todo_tools import build_default_tool_registry


@dataclass(frozen=True)
class ProcessedEvent:
    event_id: str
    route_key: str
    intent: str
    reply_text: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProcessWorkspaceEvent:
    """First application use case.

    Todo-related requests are routed through a deterministic workflow first.
    Non-Todo messages can still fall back to LLM replies for now.
    """

    def __init__(
        self,
        repository: SqliteTodoRepository | None = None,
        todo_workflow: TodoWorkflow | None = None,
    ) -> None:
        settings = get_settings()
        db_path = Path(settings.traceforge_db_path)
        self.repository = repository or SqliteTodoRepository(db_path)
        self.person_store = PersonStore(self.repository.db_path)
        self.memory_store = MarkdownMemoryStore()
        self.memory_index = build_markdown_memory_index(self.repository.db_path, self.memory_store, settings=settings)
        self.todo_workflow = todo_workflow or TodoWorkflow(self.repository, person_store=self.person_store)
        self.tool_registry = build_default_tool_registry(
            self.repository,
            workflow=self.todo_workflow,
            person_store=self.person_store,
            memory_index=self.memory_index,
        )
        self._settings = settings

    def execute(self, event: WorkspaceEvent) -> ProcessedEvent:
        text = _clean_workspace_text(
            str(event.payload.get("text") or "").strip(),
            bot_name=self._settings.zulip_bot_name,
            bot_email=self._settings.zulip_email,
        )
        command = parse_todo_command(text)
        if command.action in {TodoAction.LIST, TodoAction.SUMMARY} and "我的" in text and not command.assignee_email:
            command = replace(command, assignee_email=event.actor.email)
        evidence = [
            {
                "type": "workspace_event",
                "event_id": event.event_id,
                "source": event.source.value,
                "external_event_id": event.external_event_id,
            },
            {
                "type": "intent",
                "action": command.action.value,
                "raw_text": command.raw_text,
            },
        ]
        if command.action != TodoAction.UNKNOWN:
            result = self._call_todo_tool(event, command)
            evidence.append({"type": "tool", "tool_name": result.tool_name, "ok": result.ok})
            evidence.extend(result.evidence)
            return ProcessedEvent(
                event_id=event.event_id,
                route_key=event.route_key(),
                intent=f"todo.{command.action.value}",
                reply_text=_reply_from_tool_result(result),
                evidence=evidence,
            )

        reply = self._build_reply(event, command.action.value)
        llm_reply, llm_status = self._try_llm_reply(event, command.action.value)
        if llm_reply is not None:
            reply = llm_reply
            evidence.append({"type": "llm", "provider": "deepseek", "status": llm_status})
        return ProcessedEvent(
            event_id=event.event_id,
            route_key=event.route_key(),
            intent=command.action.value,
            reply_text=reply,
            evidence=evidence,
        )

    def _build_reply(self, event: WorkspaceEvent, intent: str) -> str:
        actor = event.actor.display_name or event.actor.email or event.actor.external_id
        topic = event.location.topic or "无 Topic"
        channel = event.location.channel_name or event.location.channel_id or "未知频道"
        return (
            f"TraceForge 已收到来自 {actor} 的请求。\n\n"
            f"- 来源：{event.source.value}\n"
            f"- 频道：{channel}\n"
            f"- Topic：{topic}\n"
            f"- 识别意图：{intent}\n\n"
            "当前是最小部署版本：已接入意图识别，Todo 链路会先走确定性应用层。"
        )

    def _try_llm_reply(self, event: WorkspaceEvent, intent: str) -> tuple[str | None, str]:
        if not self._settings.llm_enabled:
            return None, "disabled"
        try:
            return DeepSeekClient(self._settings).generate_workspace_reply(event, intent).content, "used"
        except Exception as exc:
            return (
                self._build_reply(event, intent)
                + f"\n\n[模型回复暂不可用，已使用规则回复。原因：{type(exc).__name__}]"
            ), "fallback"

    def _call_todo_tool(self, event: WorkspaceEvent, command: Any) -> ToolResult:
        tool_name = {
            TodoAction.CREATE: "todo.create",
            TodoAction.LIST: "todo.list",
            TodoAction.UPDATE: "todo.update",
            TodoAction.DELETE: "todo.delete",
            TodoAction.SUMMARY: "todo.summary",
        }.get(command.action)
        if tool_name is None:
            raise ValueError(f"Unsupported todo action: {command.action}")
        return self.tool_registry.call(
            ToolCall(
                name=tool_name,
                arguments={
                    "workspace_id": event.location.workspace_id,
                    "channel_name": event.location.channel_name,
                    "channel_id": event.location.channel_id,
                    "topic": command.topic or event.location.topic,
                    "source": event.source.value,
                    "kind": event.kind.value,
                    "actor_name": event.actor.display_name,
                    "actor_email": event.actor.email,
                    "actor_external_id": event.actor.external_id,
                    "external_event_id": event.external_event_id,
                    "raw_text": command.raw_text,
                    "title": command.title,
                    "description": command.description,
                    "todo_id": command.todo_id,
                    "assignee_name": command.assignee_name,
                    "assignee_email": command.assignee_email,
                    "status": command.status.value if command.status else None,
                    "priority": command.priority,
                },
            )
        )


def _reply_from_tool_result(result: ToolResult) -> str:
    if result.ok and isinstance(result.data, dict):
        reply_text = result.data.get("reply_text")
        if isinstance(reply_text, str) and reply_text:
            return reply_text
    if result.error:
        return result.error
    return "Todo tool executed but returned no reply text."


def _clean_workspace_text(text: str, *, bot_name: str, bot_email: str) -> str:
    cleaned = text
    for token in (
        f"@{bot_name}",
        f"@**{bot_name}**",
        bot_email,
    ):
        cleaned = cleaned.replace(token, " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()
