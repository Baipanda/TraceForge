from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from traceforge.memory.markdown_index import MarkdownMemoryIndex
from traceforge.memory.markdown_store import MarkdownMemoryStore
from traceforge.retrieval.circuit_breaker import CircuitBreaker, CircuitState
from traceforge.retrieval.retriever import Retriever, build_memory_retriever
from traceforge.retrieval.rewrite import expand_queries
from traceforge.retrieval.ttl_cache import TtlCache, make_cache_key


def _index_with_doc(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "memory" / "DECISION.md").write_text(
        "# Decisions\n\n## Auth\n\n采用 OAuth2 作为登录方案。\n",
        encoding="utf-8",
    )
    store = MarkdownMemoryStore(workspace)
    index = MarkdownMemoryIndex(tmp_path / "mem.sqlite3", store, search_mode="fts")
    return index


def test_expand_queries_returns_variants() -> None:
    queries = expand_queries("请问 OAuth2 登录方案怎么做", max_queries=3)
    assert queries[0].startswith("请问") or "OAuth2" in queries[0]
    assert len(queries) >= 1
    assert len(queries) <= 3


def test_ttl_cache_expires() -> None:
    cache: TtlCache[str] = TtlCache()
    key = make_cache_key({"corpus": "memory", "query": "a", "top_k": 3})
    cache.set(key, "hit", ttl_s=60)
    assert cache.get(key) == "hit"
    cache.set(key, "hit2", ttl_s=0)
    # ttl<=0 means do not store
    assert cache.get(key) == "hit"


def test_retriever_rewrite_and_cache(tmp_path) -> None:
    index = _index_with_doc(tmp_path)
    retriever = build_memory_retriever(
        index,
        cache_ttl_s=120,
        enable_rewrite=True,
        enable_rerank=False,
        tool_timeout_s=5,
    )
    first = retriever.search("OAuth2 登录", corpus="memory", top_k=3, kinds=("decision",))
    assert first.hits
    assert first.cached is False
    assert first.rewrite_used is True or first.subqueries
    second = retriever.search("OAuth2 登录", corpus="memory", top_k=3, kinds=("decision",))
    assert second.cached is True
    assert second.hits


def test_retriever_docs_corpus_unavailable(tmp_path) -> None:
    index = _index_with_doc(tmp_path)
    retriever = build_memory_retriever(index, enable_rewrite=False)
    result = retriever.search("OAuth2", corpus="docs", top_k=3)
    assert result.degraded is True
    assert result.degrade_reason == "corpus_unavailable"
    assert result.hits == []


def test_tool_breaker_fallback(tmp_path) -> None:
    index = _index_with_doc(tmp_path)

    class BoomIndex:
        def search_detailed(self, query, *, kinds=None, person_id=None, limit=8):
            raise RuntimeError("boom")

    breaker = CircuitBreaker(failure_threshold=2, recovery_s=30, name="test.tool")
    retriever = Retriever(
        backends={"memory": BoomIndex()},  # type: ignore[arg-type]
        tool_breaker=breaker,
        cache_ttl_s=0,
        enable_rewrite=False,
        enable_rerank=False,
        tool_timeout_s=2,
    )
    first = retriever.search("x", corpus="memory", top_k=2)
    assert first.fallback is True
    assert first.degrade_reason == "error:RuntimeError"
    second = retriever.search("x", corpus="memory", top_k=2)
    assert second.fallback is True
    assert breaker.state == CircuitState.OPEN
    third = retriever.search("x", corpus="memory", top_k=2)
    assert third.degrade_reason == "circuit_open"


@dataclass
class _OkEmbedder:
    model: str = "ok"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]


def test_memory_search_tool_uses_retriever_meta(tmp_path) -> None:
    from traceforge.tools.memory_tools import register_memory_tools
    from traceforge.tools.models import ToolCall
    from traceforge.tools.registry import ToolRegistry

    index = _index_with_doc(tmp_path)
    registry = ToolRegistry()
    register_memory_tools(registry, index=index)
    result = registry.call(ToolCall(name="memory.search", arguments={"query": "OAuth2", "limit": 3}))
    assert result.ok
    assert "corpus" in result.data
    assert "subqueries" in result.data
    assert result.data["cached"] is False
