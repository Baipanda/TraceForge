"""LLM synthesis for Topic digests (structured JSON → presentation panel)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from traceforge.application.presentation import format_datetime
from traceforge.core.todos import TodoRecord
from traceforge.infrastructure.zulip.client import ZulipTopicMessage

MAX_TRANSCRIPT_CHARS = 120_000


@dataclass(frozen=True)
class TopicDigest:
    background: str
    confirmed_facts: tuple[str, ...]
    decisions: tuple[str, ...]
    open_questions: tuple[str, ...]
    risks: tuple[str, ...]
    suggested_actions: tuple[str, ...]
    key_quotes: tuple[tuple[str, str, str], ...]  # time, speaker, excerpt


class TopicDigestModel(Protocol):
    def complete_json(self, *, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
        ...


_SYSTEM_PROMPT = """你是 TraceForge 的 Topic 摘要助手。根据 Zulip Topic 的全部聊天记录和 Todo 进展，输出结构化 JSON。

规则：
- 只基于提供的消息和 Todo，不要编造。
- 不确定的内容放入 open_questions，不要把推测写成 confirmed_facts 或 decisions。
- 使用与讨论相同的主要语言（中文 Topic 用中文）。
- 只输出一个 JSON 对象，不要 markdown 代码块。

JSON schema:
{
  "background": "string",
  "confirmed_facts": ["string"],
  "decisions": ["string"],
  "open_questions": ["string"],
  "risks": ["string"],
  "suggested_actions": ["string"],
  "key_quotes": [{"time": "string", "speaker": "string", "excerpt": "string"}]
}
"""


class TopicSummarySynthesizer:
    def __init__(self, model: TopicDigestModel) -> None:
        self.model = model

    def synthesize(
        self,
        *,
        stream: str,
        topic: str,
        messages: list[ZulipTopicMessage],
        todos: list[TodoRecord],
    ) -> TopicDigest | None:
        if not messages and not todos:
            return None
        user_prompt = self._build_user_prompt(
            stream=stream, topic=topic, messages=messages, todos=todos
        )
        raw = self.model.complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=2500,
        )
        return _parse_digest_json(raw)

    def _build_user_prompt(
        self,
        *,
        stream: str,
        topic: str,
        messages: list[ZulipTopicMessage],
        todos: list[TodoRecord],
    ) -> str:
        lines = [f"Stream: {stream}", f"Topic: {topic}", f"消息总数: {len(messages)}", ""]
        lines.append("=== Topic 消息（时间序） ===")
        transcript, truncated = _format_transcript(messages)
        lines.append(transcript)
        if truncated:
            lines.append(
                f"\n[注：最早的部分消息因长度限制未纳入 transcript，已保留最近 {MAX_TRANSCRIPT_CHARS} 字符]"
            )
        lines.append("\n=== 本 Topic Todo ===")
        if not todos:
            lines.append("（无 Todo）")
        else:
            for todo in todos:
                assignee = todo.assignee_name or todo.assignee_email or "未指定"
                completed = format_datetime(todo.completed_at) if todo.completed_at else "—"
                lines.append(
                    f"- [{todo.status.value}] {todo.title} | 执行者: {assignee} | 完成: {completed}"
                )
        return "\n".join(lines)


def _format_transcript(messages: list[ZulipTopicMessage]) -> tuple[str, bool]:
    rows: list[str] = []
    total = 0
    truncated = False
    for msg in messages:
        line = (
            f"[{format_datetime(msg.timestamp)}] {msg.sender_name}: {msg.content[:500]}"
        )
        if total + len(line) + 1 > MAX_TRANSCRIPT_CHARS:
            truncated = True
            break
        rows.append(line)
        total += len(line) + 1
    if truncated and len(messages) > len(rows):
        # Keep most recent messages when truncating from the end of iteration - actually we're iterating oldest first
        # Rebuild keeping tail
        rows = []
        total = 0
        for msg in reversed(messages):
            line = f"[{format_datetime(msg.timestamp)}] {msg.sender_name}: {msg.content[:500]}"
            if total + len(line) + 1 > MAX_TRANSCRIPT_CHARS:
                break
            rows.insert(0, line)
            total += len(line) + 1
    return "\n".join(rows), truncated


def _parse_digest_json(raw: str) -> TopicDigest:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("digest must be a JSON object")

    def strings(key: str) -> tuple[str, ...]:
        value = data.get(key) or []
        if isinstance(value, str):
            return (value,) if value.strip() else ()
        if not isinstance(value, list):
            return ()
        return tuple(str(item).strip() for item in value if str(item).strip())

    quotes: list[tuple[str, str, str]] = []
    raw_quotes = data.get("key_quotes") or []
    if isinstance(raw_quotes, list):
        for item in raw_quotes[:8]:
            if not isinstance(item, dict):
                continue
            quotes.append(
                (
                    str(item.get("time") or "—"),
                    str(item.get("speaker") or "—"),
                    str(item.get("excerpt") or "—")[:120],
                )
            )

    return TopicDigest(
        background=str(data.get("background") or "").strip(),
        confirmed_facts=strings("confirmed_facts"),
        decisions=strings("decisions"),
        open_questions=strings("open_questions"),
        risks=strings("risks"),
        suggested_actions=strings("suggested_actions"),
        key_quotes=tuple(quotes),
    )
