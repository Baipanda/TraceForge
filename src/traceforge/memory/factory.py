"""Build Markdown memory index with optional embedding provider."""

from __future__ import annotations

from pathlib import Path

from traceforge.config import TraceForgeSettings, get_settings
from traceforge.memory.embeddings import build_embedding_provider
from traceforge.memory.markdown_index import MarkdownMemoryIndex, MemorySearchMode
from traceforge.memory.markdown_store import MarkdownMemoryStore


def _resolve_provider(settings: TraceForgeSettings) -> str:
    provider = settings.memory_embedding_provider
    if provider != "auto":
        return provider
    if settings.memory_embedding_api_key and settings.memory_embedding_fallback == "http":
        return "http"
    return "local"


def _local_fastembed_available() -> bool:
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


def build_markdown_memory_index(
    db_path: str | Path,
    store: MarkdownMemoryStore | None = None,
    *,
    settings: TraceForgeSettings | None = None,
) -> MarkdownMemoryIndex:
    settings = settings or get_settings()
    provider = _resolve_provider(settings)
    if provider == "local" and not _local_fastembed_available():
        fallback = settings.memory_embedding_fallback
        if fallback == "http" and settings.memory_embedding_api_key:
            provider = "http"
        elif fallback == "hash":
            provider = "hash"
        else:
            provider = "none"

    embedder = build_embedding_provider(
        enabled=settings.memory_embedding_enabled,
        provider=provider,
        api_key=settings.memory_embedding_api_key,
        base_url=settings.memory_embedding_base_url,
        model=settings.memory_embedding_model,
        cache_dir=settings.memory_embedding_cache_dir,
    )

    search_mode: MemorySearchMode = "fts"
    if embedder is not None:
        mode = settings.memory_search_mode
        if mode in {"fts", "vector", "hybrid"}:
            search_mode = mode  # type: ignore[assignment]
        else:
            search_mode = "hybrid"

    return MarkdownMemoryIndex(
        db_path,
        store,
        embedder=embedder,
        search_mode=search_mode,
        hybrid_fts_weight=settings.memory_hybrid_fts_weight,
    )
