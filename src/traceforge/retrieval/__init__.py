"""Unified retrieval pipeline for memory and docs corpora.

Import from submodules to avoid circular imports with memory.markdown_index:
  from traceforge.retrieval.circuit_breaker import CircuitBreaker
  from traceforge.retrieval.retriever import Retriever, build_memory_retriever
"""

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "RetrievalResult",
    "Retriever",
    "TtlCache",
    "build_memory_retriever",
    "default_fallback",
    "make_cache_key",
]


def __getattr__(name: str):
    if name in {"CircuitBreaker", "CircuitState"}:
        from traceforge.retrieval import circuit_breaker as mod

        return getattr(mod, name)
    if name in {"RetrievalResult"}:
        from traceforge.retrieval.models import RetrievalResult

        return RetrievalResult
    if name in {"Retriever", "build_memory_retriever", "default_fallback"}:
        from traceforge.retrieval import retriever as mod

        return getattr(mod, name)
    if name in {"TtlCache", "make_cache_key"}:
        from traceforge.retrieval import ttl_cache as mod

        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
