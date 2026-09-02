"""Write situational memory from product events into Markdown + reindex."""

from __future__ import annotations

from typing import Any

from traceforge.application.topic_summary_synthesizer import TopicDigest
from traceforge.core.todos import TodoRecord
from traceforge.memory.markdown_index import MarkdownMemoryIndex
from traceforge.memory.markdown_store import MarkdownMemoryStore


class MemoryEventWriter:
    def __init__(
        self,
        store: MarkdownMemoryStore,
        index: MarkdownMemoryIndex | None = None,
    ) -> None:
        self.store = store
        self.index = index

    def record_topic_summary(
        self,
        *,
        stream: str | None,
        topic: str | None,
        reply_text: str,
        digest: TopicDigest | None,
        message_count: int,
        todo_count: int,
    ) -> None:
        topic = topic or "-"
        stream = stream or "-"
        if digest is not None:
            daily = (
                f"Topic 摘要：#{stream} / {topic}\n"
                f"- messages={message_count} todos={todo_count}\n"
                f"- background: {digest.background}\n"
                f"- facts: {'；'.join(digest.confirmed_facts[:8]) or '-'}\n"
                f"- open: {'；'.join(digest.open_questions[:6]) or '-'}\n"
            )
            self.store.append_daily(daily, source="topic_summary")
            if digest.decisions:
                self.store.append_decision(
                    "；".join(digest.decisions[:10]),
                    source="topic_summary",
                    topic=topic,
                )
            else:
                self.store.append_decision(
                    f"已对 #{stream}/{topic} 做 Topic 摘要（无明确 decisions 字段）。",
                    source="topic_summary",
                    topic=topic,
                )
        else:
            snippet = (reply_text or "").strip().replace("\n", " ")
            if len(snippet) > 500:
                snippet = snippet[:497] + "..."
            self.store.append_daily(
                f"Topic 摘要（fallback）：#{stream} / {topic}\n{snippet}",
                source="topic_summary",
            )
            self.store.append_decision(
                f"Topic 摘要已生成（fallback）：#{stream}/{topic}，messages={message_count}。",
                source="topic_summary",
                topic=topic,
            )
        self._reindex()

    def record_todo_change(
        self,
        *,
        action: str,
        todo: TodoRecord | None,
        topic: str | None = None,
    ) -> None:
        if todo is None:
            return
        topic = topic or todo.topic or "-"
        line = (
            f"Todo {action}: 「{todo.title}」 "
            f"status={todo.status.value if hasattr(todo.status, 'value') else todo.status} "
            f"assignee={todo.assignee_name or todo.assignee_email or '-'} "
            f"subtree={todo.subtree_label or todo.subtree_id or '-'}"
        )
        self.store.append_decision(line, source=f"todo.{action}", topic=topic)
        self.store.append_daily(line, source=f"todo.{action}")
        self._reindex()

    def _reindex(self) -> None:
        if self.index is not None:
            self.index.reindex_all()
