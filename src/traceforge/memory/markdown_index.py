"""SQLite FTS + optional embedding hybrid index over workspace Markdown memory."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from traceforge.memory.embeddings import (
    EmbeddingProvider,
    content_hash,
    cosine_similarity,
    vector_from_blob,
    vector_to_blob,
)
from traceforge.memory.markdown_store import MarkdownMemoryStore, MemoryKind

MemorySearchMode = Literal["fts", "vector", "hybrid"]


@dataclass(frozen=True)
class MemoryChunkHit:
    path: str
    kind: MemoryKind
    person_id: str | None
    title: str
    content: str
    score: float = 0.0
    fts_score: float = 0.0
    vector_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "kind": self.kind,
            "person_id": self.person_id,
            "title": self.title,
            "content": self.content,
            "score": self.score,
            "fts_score": self.fts_score,
            "vector_score": self.vector_score,
        }


class MarkdownMemoryIndex:
    """Derived search index; Markdown remains the source of truth."""

    def __init__(
        self,
        db_path: str | Path,
        store: MarkdownMemoryStore | None = None,
        *,
        embedder: EmbeddingProvider | None = None,
        search_mode: MemorySearchMode = "hybrid",
        hybrid_fts_weight: float = 0.5,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = store or MarkdownMemoryStore()
        self.embedder = embedder
        self.search_mode = search_mode if embedder is not None else "fts"
        self.hybrid_fts_weight = min(1.0, max(0.0, hybrid_fts_weight))
        self._ensure_schema()
        self.reindex_all()

    def reindex_all(self) -> int:
        refs = self.store.iter_indexable_files()
        with self._connect() as conn:
            conn.execute("DELETE FROM memory_md_chunks")
            conn.execute("DELETE FROM memory_md_fts")
            count = 0
            pending: list[tuple[int, str]] = []
            for ref in refs:
                text = ref.absolute_path.read_text(encoding="utf-8")
                for title, chunk in _chunk_markdown(text):
                    digest = content_hash(chunk)
                    conn.execute(
                        """
                        INSERT INTO memory_md_chunks (path, kind, person_id, title, content, content_hash, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                        """,
                        (ref.relative_path, ref.kind, ref.person_id, title, chunk, digest),
                    )
                    rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.execute(
                        "INSERT INTO memory_md_fts (rowid, content, path, kind, person_id, title) VALUES (?, ?, ?, ?, ?, ?)",
                        (rowid, chunk, ref.relative_path, ref.kind, ref.person_id or "", title),
                    )
                    pending.append((int(rowid), chunk))
                    count += 1
        self._ensure_embeddings(pending)
        return count

    def reindex_path(self, relative_path: str) -> int:
        self.reindex_all()
        return 1

    def search(
        self,
        query: str,
        *,
        kinds: tuple[str, ...] | None = None,
        person_id: str | None = None,
        limit: int = 8,
    ) -> list[MemoryChunkHit]:
        query = (query or "").strip()
        if not query:
            return []
        kinds = kinds or ("daily", "decision", "core", "preference")
        limit = max(1, min(limit, 20))
        mode = self.search_mode if self.embedder is not None else "fts"
        if mode == "fts":
            hits = self._search_fts(query, kinds=kinds, person_id=person_id, limit=limit)
            if hits:
                return hits
            return self._search_like(query, kinds=kinds, person_id=person_id, limit=limit)
        if mode == "vector":
            hits = self._search_vector(query, kinds=kinds, person_id=person_id, limit=limit)
            if hits:
                return hits
            return self._search_like(query, kinds=kinds, person_id=person_id, limit=limit)
        return self._search_hybrid(query, kinds=kinds, person_id=person_id, limit=limit)

    def get_file(self, relative_path: str, *, max_chars: int = 4000) -> dict[str, Any]:
        text = self.store.read_file(relative_path)
        truncated = len(text) > max_chars
        return {
            "path": relative_path,
            "content": text[:max_chars],
            "truncated": truncated,
            "chars": len(text),
        }

    def _search_hybrid(
        self,
        query: str,
        *,
        kinds: tuple[str, ...],
        person_id: str | None,
        limit: int,
    ) -> list[MemoryChunkHit]:
        candidate_limit = min(limit * 3, 30)
        fts_hits = self._search_fts(query, kinds=kinds, person_id=person_id, limit=candidate_limit)
        vector_hits = self._search_vector(query, kinds=kinds, person_id=person_id, limit=candidate_limit)
        if not fts_hits and not vector_hits:
            return self._search_like(query, kinds=kinds, person_id=person_id, limit=limit)

        merged: dict[tuple[str, str], MemoryChunkHit] = {}
        fts_norm = _rank_scores(fts_hits, score_attr="fts_score")
        for hit, norm in zip(fts_hits, fts_norm, strict=False):
            key = (hit.path, hit.title)
            merged[key] = replace(hit, fts_score=norm, score=norm * self.hybrid_fts_weight)

        vec_norm = _rank_scores(vector_hits, score_attr="vector_score")
        alpha = self.hybrid_fts_weight
        for hit, norm in zip(vector_hits, vec_norm, strict=False):
            key = (hit.path, hit.title)
            existing = merged.get(key)
            vector_weight = 1.0 - alpha
            if existing is None:
                merged[key] = replace(
                    hit,
                    vector_score=norm,
                    score=norm * vector_weight,
                )
            else:
                merged[key] = replace(
                    existing,
                    vector_score=norm,
                    score=(existing.fts_score * alpha) + (norm * vector_weight),
                )

        ranked = sorted(merged.values(), key=lambda item: item.score, reverse=True)
        return ranked[:limit]

    def _search_fts(
        self,
        query: str,
        *,
        kinds: tuple[str, ...],
        person_id: str | None,
        limit: int,
    ) -> list[MemoryChunkHit]:
        match = _fts_query(query)
        if not match:
            return []
        placeholders = ",".join("?" for _ in kinds)
        params: list[Any] = [match, *kinds]
        person_clause = ""
        if person_id:
            person_clause = " AND (c.person_id IS NULL OR c.person_id = ? OR c.kind != 'preference')"
            params.append(person_id)
        params.append(limit)
        sql = f"""
            SELECT c.path, c.kind, c.person_id, c.title, c.content,
                   bm25(memory_md_fts) AS score
            FROM memory_md_fts
            JOIN memory_md_chunks c ON c.id = memory_md_fts.rowid
            WHERE memory_md_fts MATCH ?
              AND c.kind IN ({placeholders})
              {person_clause}
            ORDER BY score
            LIMIT ?
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []
        hits = [_row_to_hit(row) for row in rows]
        return [replace(hit, fts_score=float(row["score"] or 0.0), score=float(row["score"] or 0.0)) for hit, row in zip(hits, rows, strict=False)]

    def _search_vector(
        self,
        query: str,
        *,
        kinds: tuple[str, ...],
        person_id: str | None,
        limit: int,
    ) -> list[MemoryChunkHit]:
        if self.embedder is None:
            return []
        try:
            query_vector = self.embedder.embed([query])[0]
        except Exception:
            return []

        placeholders = ",".join("?" for _ in kinds)
        params: list[Any] = [self.embedder.model, *kinds]
        person_clause = ""
        if person_id:
            person_clause = " AND (c.person_id IS NULL OR c.person_id = ? OR c.kind != 'preference')"
            params.append(person_id)

        sql = f"""
            SELECT c.path, c.kind, c.person_id, c.title, c.content, e.vector
            FROM memory_md_chunks c
            JOIN memory_md_embeddings e
              ON e.content_hash = c.content_hash AND e.model = ?
            WHERE c.kind IN ({placeholders})
              {person_clause}
        """
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        scored: list[MemoryChunkHit] = []
        for row in rows:
            vector = vector_from_blob(bytes(row["vector"]))
            similarity = cosine_similarity(query_vector, vector)
            scored.append(
                MemoryChunkHit(
                    path=str(row["path"]),
                    kind=str(row["kind"]),  # type: ignore[arg-type]
                    person_id=row["person_id"],
                    title=str(row["title"]),
                    content=str(row["content"]),
                    score=similarity,
                    vector_score=similarity,
                )
            )
        scored.sort(key=lambda item: item.vector_score, reverse=True)
        return scored[:limit]

    def _search_like(
        self,
        query: str,
        *,
        kinds: tuple[str, ...],
        person_id: str | None,
        limit: int,
    ) -> list[MemoryChunkHit]:
        tokens = _like_tokens(query)
        if not tokens:
            return []
        placeholders = ",".join("?" for _ in kinds)
        clauses = [f"c.kind IN ({placeholders})"]
        params: list[Any] = [*kinds]
        for token in tokens:
            clauses.append("c.content LIKE ?")
            params.append(f"%{token}%")
        if person_id:
            clauses.append("(c.person_id IS NULL OR c.person_id = ? OR c.kind != 'preference')")
            params.append(person_id)
        params.append(limit)
        sql = (
            "SELECT c.path, c.kind, c.person_id, c.title, c.content, 0 AS score "
            "FROM memory_md_chunks c "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY c.updated_at DESC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_hit(row) for row in rows]

    def _ensure_embeddings(self, chunks: list[tuple[int, str]]) -> None:
        if self.embedder is None or not chunks:
            return
        unique_texts: dict[str, str] = {}
        for _, text in chunks:
            unique_texts[content_hash(text)] = text
        missing: list[tuple[str, str]] = []
        with self._connect() as conn:
            for digest, text in unique_texts.items():
                row = conn.execute(
                    "SELECT 1 FROM memory_md_embeddings WHERE content_hash = ? AND model = ?",
                    (digest, self.embedder.model),
                ).fetchone()
                if row is None:
                    missing.append((digest, text))
        if not missing:
            return

        batch_size = 16
        for start in range(0, len(missing), batch_size):
            batch = missing[start : start + batch_size]
            try:
                vectors = self.embedder.embed([text for _, text in batch])
            except Exception:
                return
            with self._connect() as conn:
                for (digest, _), vector in zip(batch, vectors, strict=True):
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO memory_md_embeddings
                            (content_hash, model, dims, vector)
                        VALUES (?, ?, ?, ?)
                        """,
                        (digest, self.embedder.model, len(vector), vector_to_blob(vector)),
                    )

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_md_chunks (
                    id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    person_id TEXT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_md_chunks_path ON memory_md_chunks(path);
                CREATE INDEX IF NOT EXISTS idx_memory_md_chunks_kind ON memory_md_chunks(kind);

                CREATE VIRTUAL TABLE IF NOT EXISTS memory_md_fts USING fts5(
                    content,
                    path,
                    kind,
                    person_id,
                    title,
                    tokenize = 'unicode61'
                );

                CREATE TABLE IF NOT EXISTS memory_md_embeddings (
                    content_hash TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dims INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    PRIMARY KEY (content_hash, model)
                );
                """
            )
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(memory_md_chunks)").fetchall()
            }
            if "content_hash" not in columns:
                conn.execute("ALTER TABLE memory_md_chunks ADD COLUMN content_hash TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_md_chunks_hash ON memory_md_chunks(content_hash)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _chunk_markdown(text: str, *, max_chars: int = 800) -> list[tuple[str, str]]:
    text = text.strip()
    if not text:
        return []
    sections = re.split(r"(?m)(?=^##\s+)", text)
    chunks: list[tuple[str, str]] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        title_match = re.match(r"^##\s+(.+)$", section, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else section.splitlines()[0][:80]
        if len(section) <= max_chars:
            chunks.append((title, section))
            continue
        start = 0
        part = 1
        while start < len(section):
            end = min(len(section), start + max_chars)
            piece = section[start:end].strip()
            if piece:
                chunks.append((f"{title} ({part})", piece))
                part += 1
            start = end
    return chunks


def _fts_query(query: str) -> str | None:
    terms = re.findall(r"[\w\u4e00-\u9fff]+", query)
    cleaned: list[str] = []
    for term in terms:
        if len(term) == 1 and "\u4e00" <= term <= "\u9fff":
            continue
        cleaned.append(term.replace('"', ""))
    if not cleaned:
        cjk = "".join(ch for ch in query if "\u4e00" <= ch <= "\u9fff")
        if len(cjk) >= 2:
            cleaned = [cjk[i : i + 2] for i in range(len(cjk) - 1)]
    if not cleaned:
        return None
    return " OR ".join(f'"{term}"' for term in cleaned[:12])


def _like_tokens(query: str) -> list[str]:
    terms = re.findall(r"[\w\u4e00-\u9fff]{2,}", query)
    if terms:
        return terms[:6]
    cjk = "".join(ch for ch in query if "\u4e00" <= ch <= "\u9fff")
    if len(cjk) >= 2:
        return [cjk]
    return [query.strip()][:1]


def _row_to_hit(row: sqlite3.Row) -> MemoryChunkHit:
    return MemoryChunkHit(
        path=str(row["path"]),
        kind=str(row["kind"]),  # type: ignore[arg-type]
        person_id=row["person_id"],
        title=str(row["title"]),
        content=str(row["content"]),
        score=float(row["score"] or 0.0),
    )


def _rank_scores(hits: list[MemoryChunkHit], *, score_attr: str) -> list[float]:
    if not hits:
        return []
    if score_attr == "vector_score":
        values = [getattr(hit, score_attr) for hit in hits]
        min_value = min(values)
        max_value = max(values)
        if max_value == min_value:
            return [1.0 for _ in hits]
        return [(value - min_value) / (max_value - min_value) for value in values]

    # bm25: lower raw score is better in SQLite FTS5.
    total = len(hits)
    return [(total - index) / total for index in range(total)]
