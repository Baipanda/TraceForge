"""Topic summary: fetch full Zulip Topic history + Todo progress + LLM digest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from traceforge.application.presentation import (
    format_topic_digest_reply,
    format_topic_summary_fallback_reply,
)
from traceforge.application.topic_summary_synthesizer import (
    TopicDigest,
    TopicSummarySynthesizer,
    _format_transcript,
)
from traceforge.core.todos import TodoFilter, TodoRecord
from traceforge.infrastructure.zulip.client import ZulipApiClient, ZulipTopicMessage


class TodoListPort(Protocol):
    def list_todos(self, todo_filter: TodoFilter) -> list[TodoRecord]:
        ...


@dataclass(frozen=True)
class TopicSummaryResult:
    reply_text: str
    messages: list[ZulipTopicMessage]
    todos: list[TodoRecord]
    digest: TopicDigest | None
    evidence: list[dict[str, object]]


class TopicSummaryWorkflow:
    def __init__(
        self,
        repository: TodoListPort,
        *,
        zulip_client: ZulipApiClient | None = None,
        synthesizer: TopicSummarySynthesizer | None = None,
    ) -> None:
        self.repository = repository
        self.zulip = zulip_client or ZulipApiClient()
        self.synthesizer = synthesizer

    def summarize(
        self,
        *,
        workspace_id: str,
        channel_name: str | None,
        topic: str | None,
        include_todos: bool = True,
    ) -> TopicSummaryResult:
        stream = (channel_name or "").strip()
        topic_name = (topic or "").strip()
        if not stream or not topic_name:
            return TopicSummaryResult(
                reply_text="总结 Topic 需要在 Stream/Topic 对话里使用，或显式传入 channel_name 与 topic。",
                messages=[],
                todos=[],
                digest=None,
                evidence=[{"type": "topic.summarize", "status": "missing_location"}],
            )

        try:
            messages = self.zulip.fetch_topic_messages_all(stream=stream, topic=topic_name)
        except Exception as exc:
            return TopicSummaryResult(
                reply_text=f"拉取 Topic 消息失败：{type(exc).__name__}: {exc}",
                messages=[],
                todos=[],
                digest=None,
                evidence=[
                    {
                        "type": "topic.summarize",
                        "status": "fetch_failed",
                        "error": str(exc),
                    }
                ],
            )

        todos: list[TodoRecord] = []
        if include_todos:
            todos = self.repository.list_todos(
                TodoFilter(
                    workspace_id=workspace_id,
                    topic=topic_name,
                    channel_name=stream,
                    include_description=False,
                    limit=200,
                )
            )

        if not messages and not todos:
            return TopicSummaryResult(
                reply_text=f"Topic 摘要（#{stream} / {topic_name}）\n\n当前没有可总结的消息，也没有本 Topic 下的 Todo。",
                messages=[],
                todos=[],
                digest=None,
                evidence=[
                    {
                        "type": "topic.summarize",
                        "status": "empty",
                        "stream": stream,
                        "topic": topic_name,
                    }
                ],
            )

        _, truncated = _format_transcript(messages)
        digest: TopicDigest | None = None
        llm_status = "skipped"
        if self.synthesizer is not None:
            try:
                digest = self.synthesizer.synthesize(
                    stream=stream,
                    topic=topic_name,
                    messages=messages,
                    todos=todos,
                )
                llm_status = "ok" if digest is not None else "empty"
            except Exception as exc:
                llm_status = f"failed:{type(exc).__name__}"

        if digest is not None:
            reply = format_topic_digest_reply(
                stream=stream,
                topic=topic_name,
                message_count=len(messages),
                todos=todos,
                digest=digest,
                truncated=truncated,
            )
        else:
            reason = "未配置模型" if self.synthesizer is None else "模型摘要失败或返回为空"
            if llm_status.startswith("failed:"):
                reason = llm_status.replace("failed:", "模型错误：")
            reply = format_topic_summary_fallback_reply(
                stream=stream,
                topic=topic_name,
                message_count=len(messages),
                todos=todos,
                reason=reason,
            )

        return TopicSummaryResult(
            reply_text=reply,
            messages=messages,
            todos=todos,
            digest=digest,
            evidence=[
                {
                    "type": "topic.summarize",
                    "status": "ok" if digest else "fallback",
                    "stream": stream,
                    "topic": topic_name,
                    "message_count": len(messages),
                    "todo_count": len(todos),
                    "llm": llm_status,
                    "truncated": truncated,
                }
            ],
        )
