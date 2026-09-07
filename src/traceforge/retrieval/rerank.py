"""Optional LLM rerank; soft-fail returns input order unchanged."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol, Sequence

from traceforge.memory.markdown_index import MemoryChunkHit

logger = logging.getLogger(__name__)


class RerankClient(Protocol):
    def complete_json(self, *, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
        ...


def llm_rerank(
    query: str,
    hits: Sequence[MemoryChunkHit],
    *,
    client: RerankClient | None,
    top_k: int,
) -> tuple[list[MemoryChunkHit], bool]:
    """Return (ordered_hits[:top_k], reranked_flag). Never raises."""
    if not hits:
        return [], False
    if client is None or len(hits) <= 1:
        return list(hits)[:top_k], False
    capped = list(hits)[: min(len(hits), 15)]
    payload = [
        {
            "index": index,
            "title": hit.title,
            "path": hit.path,
            "content": hit.content[:400],
        }
        for index, hit in enumerate(capped)
    ]
    system = (
        "你是检索重排器。根据用户查询对候选片段按相关性从高到低排序。"
        "只输出 JSON：{\"order\":[index,...]}，index 为候选编号，勿输出其它文字。"
    )
    user = f"查询：{query}\n候选：{json.dumps(payload, ensure_ascii=False)}"
    try:
        raw = client.complete_json(system_prompt=system, user_prompt=user, max_tokens=400)
        order = _parse_order(raw, n=len(capped))
        if not order:
            return list(hits)[:top_k], False
        ranked = [capped[i] for i in order]
        # Append any missing candidates in original order.
        seen = set(order)
        for index, hit in enumerate(capped):
            if index not in seen:
                ranked.append(hit)
        return ranked[:top_k], True
    except Exception as exc:  # noqa: BLE001
        logger.info("llm rerank skipped: %s", type(exc).__name__)
        return list(hits)[:top_k], False


def _parse_order(raw: str, *, n: int) -> list[int]:
    text = (raw or "").strip()
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    order = data.get("order")
    if not isinstance(order, list):
        return []
    out: list[int] = []
    seen: set[int] = set()
    for item in order:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= index < n and index not in seen:
            seen.add(index)
            out.append(index)
    return out
