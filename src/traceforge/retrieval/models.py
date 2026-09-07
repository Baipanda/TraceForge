"""Retriever result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from traceforge.memory.markdown_index import MemoryChunkHit


@dataclass
class RetrievalResult:
    hits: list[MemoryChunkHit]
    corpus: str
    query: str
    top_k: int
    requested_mode: str = "hybrid"
    effective_mode: str = "hybrid"
    degraded: bool = False
    degrade_reason: str | None = None
    cached: bool = False
    rewrite_used: bool = False
    subqueries: list[str] = field(default_factory=list)
    reranked: bool = False
    fallback: bool = False
    latency_ms: float = 0.0
    breaker_state: str = "closed"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.hits),
            "hits": [hit.to_dict() for hit in self.hits],
            "corpus": self.corpus,
            "query": self.query,
            "top_k": self.top_k,
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode,
            "degraded": self.degraded,
            "degrade_reason": self.degrade_reason,
            "cached": self.cached,
            "rewrite_used": self.rewrite_used,
            "subqueries": list(self.subqueries),
            "reranked": self.reranked,
            "fallback": self.fallback,
            "latency_ms": self.latency_ms,
            "breaker_state": self.breaker_state,
            "notes": list(self.notes),
        }
