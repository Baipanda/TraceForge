"""Minimal MCP client helpers (stdio) for TraceForge tools."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpServerSpec:
    name: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] | None = None


def run_coro_sync(coro: Any, *, timeout_seconds: float = 90) -> Any:
    """Run async coroutine from sync tool handlers (safe under running event loop)."""

    def _runner() -> Any:
        return asyncio.run(coro)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_runner).result(timeout=timeout_seconds)


async def mcp_list_tools(spec: McpServerSpec) -> list[dict[str, Any]]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=spec.command,
        args=list(spec.args),
        env=_merged_env(spec.env),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = getattr(listed, "tools", None) or []
            out: list[dict[str, Any]] = []
            for tool in tools:
                out.append(
                    {
                        "name": getattr(tool, "name", ""),
                        "description": getattr(tool, "description", "") or "",
                        "inputSchema": getattr(tool, "inputSchema", None)
                        or getattr(tool, "input_schema", None)
                        or {},
                    }
                )
            return out


async def mcp_call_tool(
    spec: McpServerSpec,
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=spec.command,
        args=list(spec.args),
        env=_merged_env(spec.env),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            return _normalize_call_result(result)


def call_tool_sync(
    spec: McpServerSpec,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float = 90,
) -> dict[str, Any]:
    return run_coro_sync(
        mcp_call_tool(spec, tool_name=tool_name, arguments=arguments),
        timeout_seconds=timeout_seconds,
    )


def list_tools_sync(spec: McpServerSpec, *, timeout_seconds: float = 90) -> list[dict[str, Any]]:
    return run_coro_sync(mcp_list_tools(spec), timeout_seconds=timeout_seconds)


def _merged_env(extra: dict[str, str] | None) -> dict[str, str]:
    env = dict(os.environ)
    if extra:
        env.update({k: v for k, v in extra.items() if v is not None})
    return env


def _normalize_call_result(result: Any) -> dict[str, Any]:
    is_error = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
    content = getattr(result, "content", None) or []
    texts: list[str] = []
    structured: Any = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    for item in content:
        text = getattr(item, "text", None)
        if text:
            texts.append(str(text))
            continue
        if isinstance(item, dict) and item.get("text"):
            texts.append(str(item["text"]))
    return {
        "ok": not is_error,
        "text": "\n".join(texts).strip(),
        "texts": texts,
        "structured": structured,
        "raw_type": type(result).__name__,
    }
