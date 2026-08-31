"""Zulip Topic summary tools."""

from __future__ import annotations

from typing import Any

from traceforge.application.topic_summary import TopicSummaryWorkflow
from traceforge.application.topic_summary_synthesizer import TopicSummarySynthesizer
from traceforge.config import TraceForgeSettings, get_settings
from traceforge.infrastructure.llm.deepseek import DeepSeekClient
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository
from traceforge.infrastructure.zulip.client import ZulipApiClient
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry


def register_zulip_tools(
    registry: ToolRegistry,
    repository: SqliteTodoRepository,
    *,
    zulip_client: ZulipApiClient | None = None,
    settings: TraceForgeSettings | None = None,
) -> None:
    settings = settings or get_settings()
    synthesizer = None
    if settings.llm_enabled:
        synthesizer = TopicSummarySynthesizer(DeepSeekClient(settings))
    workflow = TopicSummaryWorkflow(
        repository,
        zulip_client=zulip_client,
        synthesizer=synthesizer,
    )

    def _summarize(arguments: dict[str, Any]) -> ToolResult:
        result = workflow.summarize(
            workspace_id=str(arguments.get("workspace_id") or "default"),
            channel_name=arguments.get("channel_name"),
            topic=arguments.get("topic"),
            include_todos=_parse_bool(arguments.get("include_todos"), default=True),
        )
        return ToolResult(
            tool_name="topic.summarize",
            ok=True,
            data={
                "reply_text": result.reply_text,
                "message_count": len(result.messages),
                "todo_count": len(result.todos),
                "has_digest": result.digest is not None,
            },
            evidence=result.evidence,
        )

    schema = {
        "type": "object",
        "properties": {
            "workspace_id": {"type": "string"},
            "channel_name": {"type": "string"},
            "topic": {"type": "string"},
            "include_todos": {"type": "boolean"},
        },
        "required": ["workspace_id"],
    }

    registry.register(
        RegisteredTool(
            name="topic.summarize",
            description=(
                "Summarize an entire Zulip Topic: fetch all messages via API, "
                "include Todo progress, return a fixed reply_text digest panel."
            ),
            schema=schema,
            handler=_summarize,
        )
    )
    registry.register(
        RegisteredTool(
            name="zulip.fetch_topic",
            description="Alias of topic.summarize for skill compatibility.",
            schema=schema,
            handler=lambda arguments: _alias_fetch(arguments, _summarize),
        )
    )


def _alias_fetch(arguments: dict[str, Any], summarize) -> ToolResult:
    result = summarize(arguments)
    return ToolResult(
        tool_name="zulip.fetch_topic",
        ok=result.ok,
        data=result.data,
        error=result.error,
        evidence=result.evidence,
        call_id=result.call_id,
    )


def _parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
