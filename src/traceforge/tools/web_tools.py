"""Web search tools backed by Tavily MCP."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from traceforge.config import TraceForgeSettings, get_settings
from traceforge.mcp import call_tool_sync, list_tools_sync
from traceforge.mcp.tavily import resolve_tavily_search_tool_name, tavily_mcp_spec
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry

logger = logging.getLogger(__name__)


def register_web_tools(registry: ToolRegistry, *, settings: TraceForgeSettings | None = None) -> None:
    settings = settings or get_settings()
    registry.register(
        RegisteredTool(
            name="web.search",
            description=(
                "Search the public web via Tavily MCP and return titles, URLs, and snippets. "
                "Use when the user asks to 网上查一下 / 搜索 / search the web / look up online. "
                "Always cite links from tool results; do not invent URLs."
            ),
            schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query in the user's language",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5, max 10)",
                    },
                },
                "required": ["query"],
            },
            handler=lambda args: _web_search(args, settings=settings),
            source="mcp:tavily",
        )
    )


def _web_search(arguments: dict[str, Any], *, settings: TraceForgeSettings) -> ToolResult:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return ToolResult(tool_name="web.search", ok=False, error="query is required")
    if not (settings.tavily_api_key or "").strip():
        return ToolResult(
            tool_name="web.search",
            ok=False,
            error="TAVILY_API_KEY is not configured",
        )

    max_results = arguments.get("max_results", 5)
    try:
        max_results_i = max(1, min(int(max_results), 10))
    except (TypeError, ValueError):
        max_results_i = 5

    spec = tavily_mcp_spec(settings)
    try:
        tools = list_tools_sync(spec, timeout_seconds=120)
        tool_name = resolve_tavily_search_tool_name([t["name"] for t in tools if t.get("name")])
        if not tool_name:
            return ToolResult(
                tool_name="web.search",
                ok=False,
                error=f"Tavily MCP has no search tool; got={[t.get('name') for t in tools]}",
            )
        raw = call_tool_sync(
            spec,
            tool_name=tool_name,
            arguments={"query": query, "max_results": max_results_i},
            timeout_seconds=120,
        )
    except Exception as exc:
        logger.exception("Tavily MCP web.search failed")
        return ToolResult(tool_name="web.search", ok=False, error=str(exc))

    if not raw.get("ok", True) and not raw.get("text") and not raw.get("structured"):
        return ToolResult(
            tool_name="web.search",
            ok=False,
            error=raw.get("text") or "Tavily MCP returned an error",
            evidence=[{"type": "mcp_error", "server": "tavily", "raw": _safe_raw(raw)}],
        )

    results = _parse_results(raw, limit=max_results_i)
    reply = _format_reply(query, results)
    return ToolResult(
        tool_name="web.search",
        ok=True,
        data={
            "query": query,
            "results": results,
            "reply_text": reply,
            "mcp_tool": tool_name,
        },
        evidence=[
            {
                "type": "web_search",
                "provider": "tavily-mcp",
                "query": query,
                "result_count": len(results),
                "urls": [item["url"] for item in results if item.get("url")],
            }
        ],
    )


def _parse_results(raw: dict[str, Any], *, limit: int) -> list[dict[str, str]]:
    structured = raw.get("structured")
    if isinstance(structured, dict):
        maybe = structured.get("results") or structured.get("data")
        if isinstance(maybe, list):
            return _normalize_result_list(maybe, limit=limit)

    text = str(raw.get("text") or "").strip()
    if not text:
        return []

    # Tavily MCP often returns a plaintext "Detailed Results:" block.
    block_results = _parse_tavily_detailed_text(text, limit=limit)
    if block_results:
        return block_results

    # Try JSON payload first.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            maybe = parsed.get("results") or parsed.get("data") or parsed
            if isinstance(maybe, list):
                return _normalize_result_list(maybe, limit=limit)
        if isinstance(parsed, list):
            return _normalize_result_list(parsed, limit=limit)
    except json.JSONDecodeError:
        pass

    # Fallback: pull markdown-like links and URLs from text.
    results: list[dict[str, str]] = []
    for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", text):
        results.append(
            {
                "title": match.group(1).strip(),
                "url": match.group(2).strip(),
                "snippet": "",
            }
        )
        if len(results) >= limit:
            return results
    if results:
        return results

    for match in re.finditer(r"https?://\S+", text):
        url = match.group(0).rstrip(").,;")
        results.append({"title": _host(url), "url": url, "snippet": ""})
        if len(results) >= limit:
            break
    if results:
        return results

    # Last resort: keep a short text blob so the model still has something.
    return [{"title": "Tavily result", "url": "", "snippet": text[:1200]}]


def _parse_tavily_detailed_text(text: str, *, limit: int) -> list[dict[str, str]]:
    chunks = re.split(r"\n(?=Title:\s*)", text)
    out: list[dict[str, str]] = []
    for chunk in chunks:
        title_m = re.search(r"^Title:\s*(.+)$", chunk, re.M)
        url_m = re.search(r"^URL:\s*(https?://\S+)\s*$", chunk, re.M)
        content_m = re.search(r"^Content:\s*(.+)$", chunk, re.M | re.S)
        if not title_m and not url_m:
            continue
        title = (title_m.group(1).strip() if title_m else "") or _host(url_m.group(1) if url_m else "")
        url = url_m.group(1).strip() if url_m else ""
        snippet = ""
        if content_m:
            snippet = content_m.group(1).strip().split("\n\n")[0].strip()
            snippet = re.sub(r"\s+", " ", snippet)[:500]
        out.append({"title": title, "url": url, "snippet": snippet})
        if len(out) >= limit:
            break
    return out


def _normalize_result_list(items: list[Any], *, limit: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "").strip()
        title = str(item.get("title") or item.get("name") or _host(url) or "result").strip()
        snippet = str(
            item.get("content")
            or item.get("snippet")
            or item.get("description")
            or item.get("raw_content")
            or ""
        ).strip()
        if not url and not snippet:
            continue
        out.append({"title": title, "url": url, "snippet": snippet[:500]})
        if len(out) >= limit:
            break
    return out


def _format_reply(query: str, results: list[dict[str, str]]) -> str:
    lines = [f"网上搜索「{query}」结果："]
    if not results:
        lines.append("未找到可用结果。")
        return "\n".join(lines)
    for idx, item in enumerate(results, start=1):
        title = item.get("title") or "untitled"
        url = item.get("url") or ""
        snippet = item.get("snippet") or ""
        if url:
            lines.append(f"{idx}. [{title}]({url})")
        else:
            lines.append(f"{idx}. {title}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _safe_raw(raw: dict[str, Any]) -> dict[str, Any]:
    text = str(raw.get("text") or "")
    return {
        "ok": raw.get("ok"),
        "text_preview": text[:500],
        "has_structured": raw.get("structured") is not None,
    }
