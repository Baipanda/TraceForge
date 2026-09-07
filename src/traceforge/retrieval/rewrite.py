"""Query rewrite: rule-based multi-query expansion (LLM optional later)."""

from __future__ import annotations

import re
from typing import Sequence

_QUESTION_TRIM = re.compile(
    r"^(请问|请帮我|帮我|怎么|如何|什么是|有没有|是否|能否|可以吗)[:：\s]*"
)
_SPLIT = re.compile(r"[\s,，。？?！!;；、]+")


def expand_queries(query: str, *, max_queries: int = 3) -> list[str]:
    """Return original + lightweight variants. Soft-fail friendly (never raises)."""
    text = (query or "").strip()
    if not text:
        return []
    out: list[str] = [text]
    trimmed = _QUESTION_TRIM.sub("", text).strip()
    if trimmed and trimmed not in out:
        out.append(trimmed)
    tokens = [tok for tok in _SPLIT.split(trimmed or text) if len(tok) >= 2]
    if len(tokens) >= 2:
        joined = " ".join(tokens[:4])
        if joined not in out:
            out.append(joined)
    # Prefer distinctive tokens as a short subquery.
    if tokens:
        distinctive = sorted(tokens, key=len, reverse=True)[:2]
        short = " ".join(distinctive)
        if short not in out:
            out.append(short)
    return out[: max(1, max_queries)]


def merge_subquery_lists(primary: Sequence[str], extra: Sequence[str], *, max_queries: int) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for item in [*primary, *extra]:
        text = (item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
        if len(merged) >= max_queries:
            break
    return merged
