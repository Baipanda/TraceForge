from __future__ import annotations

from typing import Any

from traceforge.config import TraceForgeSettings, get_settings
from traceforge.infrastructure.llm.deepseek import DeepSeekClient
from traceforge.memory.markdown_index import MarkdownMemoryIndex
from traceforge.memory.markdown_store import MarkdownMemoryStore
from traceforge.retrieval.retriever import Retriever, build_memory_retriever
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry


def register_memory_tools(
    registry: ToolRegistry,
    *,
    index: MarkdownMemoryIndex,
    store: MarkdownMemoryStore | None = None,
    retriever: Retriever | None = None,
    settings: TraceForgeSettings | None = None,
) -> None:
    store = store or index.store
    settings = settings or get_settings()
    retriever = retriever or _build_retriever(index, settings)

    registry.register(
        RegisteredTool(
            name="memory.search",
            description=(
                "Search Markdown memory (daily notes, decisions, core, preferences) via the "
                "unified retriever: TTL cache → query rewrite → parallel FTS∥vector → merge → "
                "optional LLM rerank. Embed failures degrade to FTS; tool-level timeout/breaker "
                "uses fallback with degrade_reason metadata."
            ),
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "kinds": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["daily", "decision", "core", "preference"],
                        },
                    },
                    "person_id": {"type": "string"},
                    "limit": {"type": "integer"},
                    "corpus": {
                        "type": "string",
                        "enum": ["memory", "docs"],
                        "description": "Default memory; docs when a docs corpus is registered.",
                    },
                },
                "required": ["query"],
            },
            handler=lambda arguments: _search(retriever, arguments),
        )
    )
    registry.register(
        RegisteredTool(
            name="memory.get",
            description="Read a workspace memory Markdown file by relative path (e.g. memory/DECISION.md).",
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer"},
                },
                "required": ["path"],
            },
            handler=lambda arguments: _get(index, arguments),
        )
    )
    registry.register(
        RegisteredTool(
            name="memory.remember",
            description=(
                "Append a durable personal preference for a person_id when the user says "
                "以后/之后/记住/下次请… Write to memory/preferences/<person_id>.md and reindex."
            ),
            schema={
                "type": "object",
                "properties": {
                    "person_id": {"type": "string"},
                    "note": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["person_id", "note"],
            },
            handler=lambda arguments: _remember(store, index, arguments),
        )
    )


def _build_retriever(index: MarkdownMemoryIndex, settings: TraceForgeSettings) -> Retriever:
    rerank_client = None
    if settings.memory_retrieve_rerank and settings.llm_enabled:
        try:
            rerank_client = DeepSeekClient(settings, timeout_seconds=min(8.0, settings.memory_retrieve_timeout_s))
        except Exception:
            rerank_client = None
    return build_memory_retriever(
        index,
        cache_ttl_s=settings.memory_retrieve_cache_ttl_s,
        tool_timeout_s=settings.memory_retrieve_timeout_s,
        enable_rewrite=settings.memory_retrieve_rewrite,
        enable_rerank=settings.memory_retrieve_rerank and rerank_client is not None,
        rerank_client=rerank_client,
        tool_fail_threshold=settings.memory_retrieve_tool_fail_threshold,
        tool_recovery_s=settings.memory_retrieve_tool_recovery_s,
    )


def _search(retriever: Retriever, arguments: dict[str, Any]) -> ToolResult:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return ToolResult(tool_name="memory.search", ok=False, error="query 不能为空")
    kinds_raw = arguments.get("kinds")
    kinds: tuple[str, ...] | None = None
    if isinstance(kinds_raw, list):
        kinds = tuple(str(item) for item in kinds_raw if isinstance(item, str))
    person_id = arguments.get("person_id")
    limit = int(arguments.get("limit") or 8)
    corpus = str(arguments.get("corpus") or "memory").strip() or "memory"
    result = retriever.search(
        query,
        corpus=corpus,
        top_k=limit,
        kinds=kinds,
        person_id=str(person_id) if person_id else None,
    )
    return ToolResult(tool_name="memory.search", ok=True, data=result.to_dict())


def _get(index: MarkdownMemoryIndex, arguments: dict[str, Any]) -> ToolResult:
    path = str(arguments.get("path") or "").strip()
    if not path:
        return ToolResult(tool_name="memory.get", ok=False, error="path 不能为空")
    max_chars = int(arguments.get("max_chars") or 4000)
    payload = index.get_file(path, max_chars=max_chars)
    if not payload["content"] and payload["chars"] == 0:
        return ToolResult(
            tool_name="memory.get",
            ok=False,
            error=f"找不到记忆文件：{path}",
            data=payload,
        )
    return ToolResult(tool_name="memory.get", ok=True, data=payload)


def _remember(
    store: MarkdownMemoryStore,
    index: MarkdownMemoryIndex,
    arguments: dict[str, Any],
) -> ToolResult:
    person_id = str(arguments.get("person_id") or "").strip()
    note = str(arguments.get("note") or "").strip()
    source = str(arguments.get("source") or "agent").strip() or "agent"
    if not person_id or not note:
        return ToolResult(
            tool_name="memory.remember",
            ok=False,
            error="person_id 与 note 都必填",
        )
    path = store.append_preference(person_id, note, source=source)
    index.reindex_all()
    relative = str(path.relative_to(store.workspace_root)).replace("\\", "/")
    return ToolResult(
        tool_name="memory.remember",
        ok=True,
        data={"path": relative, "person_id": person_id, "note": note},
        evidence=[{"type": "memory.remember", "path": relative}],
    )
