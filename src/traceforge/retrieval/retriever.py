"""Unified retriever: cache → rewrite → parallel dual-path → merge → rerank.

Tool-level shell: three-state breaker + timeout + reason-aware fallback.
Embed-path FTS degrade stays inside MarkdownMemoryIndex.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from dataclasses import replace
from typing import Any, Callable, Protocol

from traceforge.memory.markdown_index import MemoryChunkHit, MarkdownMemoryIndex, MemorySearchOutcome
from traceforge.retrieval.circuit_breaker import CircuitBreaker
from traceforge.retrieval.models import RetrievalResult
from traceforge.retrieval.rerank import llm_rerank
from traceforge.retrieval.rewrite import expand_queries
from traceforge.retrieval.ttl_cache import TtlCache, make_cache_key

logger = logging.getLogger(__name__)


class DualPathIndex(Protocol):
    def search_detailed(
        self,
        query: str,
        *,
        kinds: tuple[str, ...] | None = None,
        person_id: str | None = None,
        limit: int = 8,
    ) -> MemorySearchOutcome:
        ...


FallbackFn = Callable[[str, dict[str, Any], str], RetrievalResult]


class Retriever:
    def __init__(
        self,
        *,
        backends: dict[str, DualPathIndex],
        tool_breaker: CircuitBreaker | None = None,
        cache: TtlCache[dict[str, Any]] | None = None,
        cache_ttl_s: float = 120.0,
        tool_timeout_s: float = 8.0,
        max_subqueries: int = 3,
        enable_rewrite: bool = True,
        enable_rerank: bool = False,
        rerank_client: Any | None = None,
        fallback: FallbackFn | None = None,
        name: str = "retriever",
    ) -> None:
        self.backends = backends
        self.tool_breaker = tool_breaker or CircuitBreaker(
            failure_threshold=5, recovery_s=60.0, name=f"{name}.tool"
        )
        self.cache = cache or TtlCache()
        self.cache_ttl_s = max(0.0, cache_ttl_s)
        self.tool_timeout_s = max(0.5, tool_timeout_s)
        self.max_subqueries = max(1, min(max_subqueries, 5))
        self.enable_rewrite = enable_rewrite
        self.enable_rerank = enable_rerank
        self.rerank_client = rerank_client
        self.fallback = fallback or default_fallback
        self.name = name

    def search(
        self,
        query: str,
        *,
        corpus: str = "memory",
        top_k: int = 8,
        kinds: tuple[str, ...] | None = None,
        person_id: str | None = None,
    ) -> RetrievalResult:
        query = (query or "").strip()
        top_k = max(1, min(int(top_k or 8), 20))
        params = {
            "corpus": corpus,
            "query": query,
            "top_k": top_k,
            "kinds": list(kinds) if kinds else None,
            "person_id": person_id,
        }
        t0 = time.monotonic()

        if not query:
            return RetrievalResult(
                hits=[],
                corpus=corpus,
                query=query,
                top_k=top_k,
                effective_mode="empty",
                latency_ms=0.0,
                breaker_state=self.tool_breaker.state.value,
            )

        cache_key = make_cache_key(params)
        if self.cache_ttl_s > 0:
            cached = self.cache.get(cache_key)
            if cached is not None:
                result = _result_from_dict(cached)
                result.cached = True
                result.latency_ms = (time.monotonic() - t0) * 1000
                result.breaker_state = self.tool_breaker.state.value
                return result

        if not self.tool_breaker.allow():
            return self._run_fallback(
                query,
                params,
                reason="circuit_open",
                latency_ms=(time.monotonic() - t0) * 1000,
            )

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    self._pipeline,
                    query,
                    corpus=corpus,
                    top_k=top_k,
                    kinds=kinds,
                    person_id=person_id,
                )
                result = future.result(timeout=self.tool_timeout_s)
            self.tool_breaker.record_success()
            result.latency_ms = (time.monotonic() - t0) * 1000
            result.breaker_state = self.tool_breaker.state.value
            if self.cache_ttl_s > 0 and not result.degraded and not result.fallback:
                self.cache.set(cache_key, result.to_dict(), self.cache_ttl_s)
            return result
        except FuturesTimeout:
            self.tool_breaker.record_failure()
            return self._run_fallback(
                query,
                params,
                reason="timeout",
                latency_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("retriever failed corpus=%s", corpus)
            self.tool_breaker.record_failure()
            return self._run_fallback(
                query,
                params,
                reason=f"error:{type(exc).__name__}",
                latency_ms=(time.monotonic() - t0) * 1000,
            )

    def _run_fallback(
        self,
        query: str,
        params: dict[str, Any],
        *,
        reason: str,
        latency_ms: float,
    ) -> RetrievalResult:
        result = self.fallback(query, params, reason)
        result.fallback = True
        result.degraded = True
        result.degrade_reason = reason
        result.latency_ms = latency_ms
        result.breaker_state = self.tool_breaker.state.value
        return result

    def _pipeline(
        self,
        query: str,
        *,
        corpus: str,
        top_k: int,
        kinds: tuple[str, ...] | None,
        person_id: str | None,
    ) -> RetrievalResult:
        backend = self.backends.get(corpus)
        if backend is None:
            return RetrievalResult(
                hits=[],
                corpus=corpus,
                query=query,
                top_k=top_k,
                effective_mode="unavailable",
                degraded=True,
                degrade_reason="corpus_unavailable",
                notes=[f"corpus `{corpus}` 未注册"],
            )

        notes: list[str] = []
        rewrite_used = False
        subqueries = [query]
        if self.enable_rewrite:
            try:
                expanded = expand_queries(query, max_queries=self.max_subqueries)
                if expanded:
                    subqueries = expanded
                    rewrite_used = len(subqueries) > 1
            except Exception as exc:  # noqa: BLE001
                notes.append(f"rewrite_skipped:{type(exc).__name__}")
                subqueries = [query]

        candidate_limit = min(top_k * 3, 30)
        per_query_outcomes: list[MemorySearchOutcome] = []
        max_workers = min(4, len(subqueries))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    backend.search_detailed,
                    subquery,
                    kinds=kinds,
                    person_id=person_id,
                    limit=candidate_limit,
                ): subquery
                for subquery in subqueries
            }
            for future in as_completed(futures):
                subquery = futures[future]
                try:
                    per_query_outcomes.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"subquery_failed:{subquery[:20]}:{type(exc).__name__}")

        if not per_query_outcomes:
            # Entire tool call failed — let the outer shell trip the breaker + fallback.
            raise RuntimeError("all_subqueries_failed")

        merged_hits = _merge_hits(per_query_outcomes)
        requested_mode = per_query_outcomes[0].requested_mode
        effective_modes = {item.effective_mode for item in per_query_outcomes}
        degraded = any(item.degraded for item in per_query_outcomes)
        reasons = [item.degrade_reason for item in per_query_outcomes if item.degrade_reason]
        degrade_reason = reasons[0] if reasons else None
        if len(effective_modes) == 1:
            effective_mode = next(iter(effective_modes))
        elif "hybrid" in effective_modes:
            effective_mode = "hybrid"
        else:
            effective_mode = sorted(effective_modes)[0]

        reranked = False
        final_hits = merged_hits
        if self.enable_rerank:
            final_hits, reranked = llm_rerank(
                query,
                merged_hits,
                client=self.rerank_client,
                top_k=top_k,
            )
            if not reranked:
                notes.append("rerank_skipped")
                final_hits = merged_hits[:top_k]
        else:
            final_hits = merged_hits[:top_k]

        return RetrievalResult(
            hits=final_hits,
            corpus=corpus,
            query=query,
            top_k=top_k,
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            degraded=degraded,
            degrade_reason=degrade_reason,
            rewrite_used=rewrite_used,
            subqueries=subqueries,
            reranked=reranked,
            notes=notes,
        )


def default_fallback(query: str, params: dict[str, Any], reason: str) -> RetrievalResult:
    corpus = str(params.get("corpus") or "memory")
    top_k = int(params.get("top_k") or 8)
    messages = {
        "circuit_open": "检索工具熔断中，请稍后重试",
        "timeout": "检索超时，已跳过本轮召回",
        "corpus_unavailable": "目标语料未配置",
    }
    note = messages.get(reason, f"检索失败：{reason}")
    return RetrievalResult(
        hits=[],
        corpus=corpus,
        query=query,
        top_k=top_k,
        effective_mode="fallback",
        degraded=True,
        degrade_reason=reason,
        fallback=True,
        notes=[note],
    )


def _merge_hits(outcomes: list[MemorySearchOutcome]) -> list[MemoryChunkHit]:
    merged: dict[tuple[str, str], MemoryChunkHit] = {}
    for outcome in outcomes:
        for hit in outcome.hits:
            key = (hit.path, hit.title)
            existing = merged.get(key)
            if existing is None or hit.score > existing.score:
                merged[key] = hit
            elif existing is not None:
                merged[key] = replace(
                    existing,
                    fts_score=max(existing.fts_score, hit.fts_score),
                    vector_score=max(existing.vector_score, hit.vector_score),
                    score=max(existing.score, hit.score),
                )
    return sorted(merged.values(), key=lambda item: item.score, reverse=True)


def _result_from_dict(data: dict[str, Any]) -> RetrievalResult:
    hits = [
        MemoryChunkHit(
            path=str(item.get("path") or ""),
            kind=str(item.get("kind") or "core"),  # type: ignore[arg-type]
            person_id=item.get("person_id"),
            title=str(item.get("title") or ""),
            content=str(item.get("content") or ""),
            score=float(item.get("score") or 0.0),
            fts_score=float(item.get("fts_score") or 0.0),
            vector_score=float(item.get("vector_score") or 0.0),
        )
        for item in (data.get("hits") or [])
        if isinstance(item, dict)
    ]
    return RetrievalResult(
        hits=hits,
        corpus=str(data.get("corpus") or "memory"),
        query=str(data.get("query") or ""),
        top_k=int(data.get("top_k") or 8),
        requested_mode=str(data.get("requested_mode") or "hybrid"),
        effective_mode=str(data.get("effective_mode") or "hybrid"),
        degraded=bool(data.get("degraded")),
        degrade_reason=data.get("degrade_reason"),
        cached=bool(data.get("cached")),
        rewrite_used=bool(data.get("rewrite_used")),
        subqueries=list(data.get("subqueries") or []),
        reranked=bool(data.get("reranked")),
        fallback=bool(data.get("fallback")),
        notes=list(data.get("notes") or []),
    )


def build_memory_retriever(
    index: MarkdownMemoryIndex,
    *,
    cache_ttl_s: float = 120.0,
    tool_timeout_s: float = 8.0,
    enable_rewrite: bool = True,
    enable_rerank: bool = False,
    rerank_client: Any | None = None,
    docs_index: DualPathIndex | None = None,
    tool_fail_threshold: int = 5,
    tool_recovery_s: float = 60.0,
) -> Retriever:
    backends: dict[str, DualPathIndex] = {"memory": index}
    if docs_index is not None:
        backends["docs"] = docs_index
    return Retriever(
        backends=backends,
        tool_breaker=CircuitBreaker(
            failure_threshold=tool_fail_threshold,
            recovery_s=tool_recovery_s,
            name="memory.search",
        ),
        cache_ttl_s=cache_ttl_s,
        tool_timeout_s=tool_timeout_s,
        enable_rewrite=enable_rewrite,
        enable_rerank=enable_rerank,
        rerank_client=rerank_client,
    )
