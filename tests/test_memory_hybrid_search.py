from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from traceforge.memory.markdown_index import MarkdownMemoryIndex
from traceforge.memory.markdown_store import MarkdownMemoryStore


@dataclass
class KeywordEmbeddingProvider:
    """Test helper: similar queries/chunks share axis-aligned vectors."""

    model: str = "keyword-test"
    dims: int = 8

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dims
            lowered = text.lower()
            if "oauth" in lowered or "登录" in text or "auth" in lowered or "鉴权" in text:
                vector[0] = 1.0
            if "泰安" in text or "山东" in text:
                vector[1] = 1.0
            if "todo" in lowered or "任务" in text:
                vector[2] = 1.0
            if not any(vector):
                vector[3] = 1.0
            vectors.append(vector)
        return vectors


def test_hybrid_search_merges_fts_and_vector(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "memory" / "DECISION.md").write_text(
        "# Decisions\n\n## Auth\n\n采用 OAuth2 作为登录方案。\n",
        encoding="utf-8",
    )
    store = MarkdownMemoryStore(workspace)
    embedder = KeywordEmbeddingProvider()
    index = MarkdownMemoryIndex(
        tmp_path / "mem.sqlite3",
        store,
        embedder=embedder,
        search_mode="hybrid",
        hybrid_fts_weight=0.5,
    )

    hits = index.search("登录方案", kinds=("decision",), limit=3)
    assert hits
    assert any("OAuth2" in hit.content for hit in hits)
    assert hits[0].vector_score >= 0.0
    assert hits[0].fts_score >= 0.0


def test_vector_mode_without_keyword_match(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "memory" / "DECISION.md").write_text(
        "# Decisions\n\n## Auth\n\n采用 OAuth2 作为登录方案。\n",
        encoding="utf-8",
    )
    store = MarkdownMemoryStore(workspace)
    embedder = KeywordEmbeddingProvider()
    index = MarkdownMemoryIndex(
        tmp_path / "mem.sqlite3",
        store,
        embedder=embedder,
        search_mode="vector",
    )

    hits = index.search("用户鉴权", kinds=("decision",), limit=3)
    assert hits
    assert "OAuth2" in hits[0].content


def test_hash_embedder_reindexes_and_stores_vectors(tmp_path) -> None:
    from traceforge.memory.embeddings import HashEmbeddingProvider
    import sqlite3

    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "MEMORY.md").write_text("# Core\n\nhello memory\n", encoding="utf-8")
    store = MarkdownMemoryStore(workspace)
    embedder = HashEmbeddingProvider()
    db_path = tmp_path / "mem.sqlite3"
    index = MarkdownMemoryIndex(db_path, store, embedder=embedder, search_mode="vector")

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM memory_md_embeddings").fetchone()[0]
    assert count >= 1

    hits = index.search("memory", kinds=("core",), limit=1)
    assert hits


def test_fts_fallback_when_no_embedder(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "memory").mkdir(parents=True)
    (workspace / "memory" / "DECISION.md").write_text(
        "# Decisions\n\n## Auth\n\n采用 OAuth2 作为登录方案。\n",
        encoding="utf-8",
    )
    store = MarkdownMemoryStore(workspace)
    index = MarkdownMemoryIndex(tmp_path / "mem.sqlite3", store)

    hits = index.search("OAuth2", kinds=("decision",))
    assert hits
    assert hits[0].vector_score == 0.0
