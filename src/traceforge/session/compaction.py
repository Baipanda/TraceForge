"""Session memory flush and transcript compaction (OpenClaw-inspired)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from traceforge.memory.markdown_index import MarkdownMemoryIndex
from traceforge.memory.markdown_store import MarkdownMemoryStore
from traceforge.session.transcript import (
    DEFAULT_KEEP_RECENT_TOKENS,
    JsonlSessionStore,
    SessionEvent,
    estimate_tokens,
)


FLUSH_RATIO = 0.8


class Summarizer(Protocol):
    def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 600) -> object:
        ...


@dataclass(frozen=True)
class CompactionResult:
    flushed: bool
    compacted: bool
    transcript_tokens: int
    detail: str = ""


def estimate_transcript_tokens(events: list[SessionEvent]) -> int:
    return sum(estimate_tokens((event.name or "") + " " + event.content) for event in events)


def maybe_flush_and_compact(
    *,
    session_key: str,
    store: JsonlSessionStore,
    memory_store: MarkdownMemoryStore,
    memory_index: MarkdownMemoryIndex | None = None,
    keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS,
    summarizer: Summarizer | None = None,
    topic: str | None = None,
    channel_name: str | None = None,
) -> CompactionResult:
    """Flush once near the window, then compact when over the keep budget.

    - >= 80% budget and not yet flushed this generation → write daily/decision md
    - >= 100% budget → LLM/heuristic summary + rewrite transcript to summary + recent tail
    """
    events = store.load_events(session_key)
    tokens = estimate_transcript_tokens(events)
    flush_at = max(1, int(keep_recent_tokens * FLUSH_RATIO))
    meta = _load_meta(store, session_key)
    compact_gen = int(meta.get("compact_gen") or 0)
    flush_gen = int(meta.get("flush_gen") or 0)
    flushed = False
    compacted = False
    detail_parts: list[str] = []

    if tokens >= flush_at and flush_gen <= compact_gen:
        flush_session_memory(
            events,
            memory_store=memory_store,
            session_key=session_key,
            topic=topic,
            channel_name=channel_name,
        )
        if memory_index is not None:
            memory_index.reindex_all()
        flush_gen = compact_gen + 1
        meta["flush_gen"] = flush_gen
        _save_meta(store, session_key, meta)
        flushed = True
        detail_parts.append("flushed")

    if tokens >= keep_recent_tokens:
        new_events = compact_transcript(
            events,
            keep_recent_tokens=keep_recent_tokens,
            summarizer=summarizer,
        )
        store.replace_events(session_key, new_events)
        meta["compact_gen"] = flush_gen if flush_gen > compact_gen else compact_gen + 1
        meta["flush_gen"] = meta["compact_gen"]
        _save_meta(store, session_key, meta)
        compacted = True
        detail_parts.append("compacted")

    return CompactionResult(
        flushed=flushed,
        compacted=compacted,
        transcript_tokens=tokens,
        detail="+".join(detail_parts),
    )


def flush_session_memory(
    events: list[SessionEvent],
    *,
    memory_store: MarkdownMemoryStore,
    session_key: str,
    topic: str | None = None,
    channel_name: str | None = None,
) -> None:
    lines = []
    decisions: list[str] = []
    for event in events[-40:]:
        prefix = event.type
        if event.type == "tool" and event.name:
            prefix = f"tool:{event.name}"
        snippet = event.content.strip().replace("\n", " ")
        if len(snippet) > 240:
            snippet = snippet[:237] + "..."
        lines.append(f"- [{prefix}] {snippet}")
        if event.type == "assistant" and any(
            token in event.content for token in ("决定", "结论", "约定", "采用", "确认")
        ):
            decisions.append(snippet[:200])
    header = f"session=`{session_key}` channel={channel_name or '-'} topic={topic or '-'}"
    body = header + "\n\n" + "\n".join(lines[-30:])
    memory_store.append_daily(body, source="session_flush")
    if decisions:
        memory_store.append_decision(
            "；".join(decisions[:5]),
            source="session_flush",
            topic=topic,
        )
    elif topic:
        memory_store.append_decision(
            f"会话接近上下文窗口，已 flush。Topic={topic}。详见当日 daily notes。",
            source="session_flush",
            topic=topic,
        )


def compact_transcript(
    events: list[SessionEvent],
    *,
    keep_recent_tokens: int,
    summarizer: Summarizer | None = None,
) -> list[SessionEvent]:
    if not events:
        return []
    kept: list[SessionEvent] = []
    used = 0
    for event in reversed(events):
        cost = estimate_tokens((event.name or "") + " " + event.content)
        if kept and used + cost > keep_recent_tokens:
            break
        kept.append(event)
        used += cost
    kept.reverse()
    older = events[: max(0, len(events) - len(kept))]
    if not older:
        return events
    summary = _summarize_events(older, summarizer=summarizer)
    compaction = SessionEvent(type="compaction", content=summary, name="session.compact")
    return [compaction, *kept]


def _summarize_events(events: list[SessionEvent], *, summarizer: Summarizer | None) -> str:
    transcript = []
    for event in events:
        role = event.type
        if event.type == "tool":
            role = f"tool:{event.name or 'tool'}"
        transcript.append(f"{role}: {event.content[:500]}")
    blob = "\n".join(transcript)
    if len(blob) > 12000:
        blob = blob[:12000] + "\n…(truncated)"
    if summarizer is not None:
        try:
            reply = summarizer.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是会话压缩助手。把多轮 TraceForge/Zulip 对话压缩成简洁中文摘要，"
                            "保留：人物、关键事实、已做决策、未决问题、进行中的 Todo。"
                            "不要编造。输出纯文本，不要 markdown 标题堆砌。"
                        ),
                    },
                    {"role": "user", "content": f"请压缩以下会话：\n\n{blob}"},
                ],
                max_tokens=800,
            )
            content = getattr(reply, "content", None) or str(reply)
            content = str(content).strip()
            if content:
                return content
        except Exception:
            pass
    return "会话压缩摘要（启发式）：\n" + "\n".join(line[:180] for line in transcript[:12])


def _meta_path(store: JsonlSessionStore, session_key: str) -> Path:
    return store.path_for(session_key).with_suffix(".meta.json")


def _load_meta(store: JsonlSessionStore, session_key: str) -> dict:
    path = _meta_path(store, session_key)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_meta(store: JsonlSessionStore, session_key: str, meta: dict) -> None:
    path = _meta_path(store, session_key)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
