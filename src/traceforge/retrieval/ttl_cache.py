"""Process-local TTL cache for retriever results."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class TtlCache(Generic[T]):
    def __init__(self, *, max_entries: int = 2048) -> None:
        self._max_entries = max(16, max_entries)
        self._store: dict[str, tuple[T, float]] = {}

    def get(self, key: str) -> T | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expire_at = item
        if time.monotonic() >= expire_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T, ttl_s: float) -> None:
        if ttl_s <= 0:
            return
        if len(self._store) >= self._max_entries:
            # Drop oldest ~25% insertion-order entries.
            for old_key in list(self._store)[: max(1, self._max_entries // 4)]:
                self._store.pop(old_key, None)
        self._store[key] = (value, time.monotonic() + ttl_s)

    def clear(self) -> None:
        self._store.clear()

    def invalidate_prefix(self, prefix: str) -> int:
        keys = [key for key in self._store if key.startswith(prefix)]
        for key in keys:
            self._store.pop(key, None)
        return len(keys)


def make_cache_key(parts: dict[str, Any]) -> str:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.md5(payload.encode("utf-8")).hexdigest()
    corpus = str(parts.get("corpus") or "default")
    return f"{corpus}:{digest}"
