"""Embedding providers and vector helpers for hybrid memory search."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...


class HashEmbeddingProvider:
    """Deterministic local embedder for dev/test (no semantic quality)."""

    def __init__(self, *, dims: int = 64, model: str = "hash-local") -> None:
        self.dims = max(8, dims)
        self.model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [_hash_to_vector(text, dims=self.dims) for text in texts]


class LocalEmbeddingProvider:
    """Local ONNX embeddings via fastembed (auto-download on first use).

    Similar to OpenClaw ``memorySearch.provider = local`` with a cached HF model,
    but implemented in Python instead of node-llama-cpp GGUF.
    """

    def __init__(
        self,
        *,
        model: str,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.model = model
        self._cache_dir = Path(cache_dir).expanduser() if cache_dir else None
        self._engine: object | None = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        engine = self._get_engine()
        vectors = list(engine.embed(list(texts)))
        return [vector.tolist() for vector in vectors]

    def _get_engine(self) -> object:
        if self._engine is not None:
            return self._engine
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "Local embeddings require fastembed. Install with: pip install -e '.[memory]'"
            ) from exc
        kwargs: dict[str, object] = {"model_name": self.model}
        if self._cache_dir is not None:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            kwargs["cache_dir"] = str(self._cache_dir)
        self._engine = TextEmbedding(**kwargs)
        return self._engine


class HttpEmbeddingProvider:
    """OpenAI-compatible ``POST /embeddings`` client (optional remote fallback)."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("embedding api_key is required")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model = model
        self._timeout_seconds = timeout_seconds

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        body = {"model": self.model, "input": list(texts)}
        request = urllib.request.Request(
            url=f"{self._base_url}/embeddings",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Embedding API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Embedding API request failed: {exc.reason}") from exc

        data = payload.get("data")
        if not isinstance(data, list):
            raise RuntimeError("Embedding API response missing data")
        ordered = sorted(
            (item for item in data if isinstance(item, dict)),
            key=lambda item: int(item.get("index") or 0),
        )
        vectors: list[list[float]] = []
        for item in ordered:
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise RuntimeError("Embedding API response missing embedding vector")
            vectors.append([float(value) for value in embedding])
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding API returned unexpected vector count")
        return vectors


def build_embedding_provider(
    *,
    enabled: bool,
    provider: str,
    api_key: str | None,
    base_url: str,
    model: str,
    cache_dir: str | Path | None = None,
) -> EmbeddingProvider | None:
    if not enabled:
        return None
    if provider in {"none", "off"}:
        return None
    if provider == "hash":
        return HashEmbeddingProvider(model="hash-local")
    if provider == "local":
        try:
            return LocalEmbeddingProvider(model=model, cache_dir=cache_dir)
        except RuntimeError:
            return None
    if provider == "http":
        if not api_key or not base_url:
            return None
        return HttpEmbeddingProvider(api_key=api_key, base_url=base_url, model=model)
    return None


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


def vector_to_blob(values: Sequence[float]) -> bytes:
    return struct.pack(f"{len(values)}f", *values)


def vector_from_blob(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"{count}f", blob))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_to_vector(text: str, *, dims: int) -> list[float]:
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    counter = 0
    while len(values) < dims:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for index in range(0, len(block), 4):
            if len(values) >= dims:
                break
            chunk = block[index : index + 4]
            integer = int.from_bytes(chunk, "big", signed=False)
            values.append((integer / 2**32) * 2.0 - 1.0)
        counter += 1
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]
