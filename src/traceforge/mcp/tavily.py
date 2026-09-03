"""Tavily MCP server spec helpers."""

from __future__ import annotations

from traceforge.config import TraceForgeSettings, get_settings
from traceforge.mcp import McpServerSpec


def tavily_mcp_spec(settings: TraceForgeSettings | None = None) -> McpServerSpec:
    settings = settings or get_settings()
    command = (settings.mcp_tavily_command or "npx").strip() or "npx"
    args = tuple(
        part.strip()
        for part in (settings.mcp_tavily_args or "-y,tavily-mcp@latest").split(",")
        if part.strip()
    )
    env: dict[str, str] = {}
    if settings.tavily_api_key:
        env["TAVILY_API_KEY"] = settings.tavily_api_key
    if settings.mcp_tavily_default_parameters:
        env["DEFAULT_PARAMETERS"] = settings.mcp_tavily_default_parameters

    # Keep MCP child Node away from IDE-bundled broken npm prefixes.
    from pathlib import Path

    cmd_path = Path(command)
    if cmd_path.name in {"node", "npx", "npm"} and cmd_path.parent.is_dir():
        node_root = cmd_path.parent.parent if cmd_path.parent.name == "bin" else cmd_path.parent
        bin_dir = node_root / "bin"
        path_parts = [str(bin_dir)]
        for part in (__import__("os").environ.get("PATH") or "").split(":"):
            if not part:
                continue
            if ".cursor-server" in part or "cursor-server" in part:
                continue
            if part not in path_parts:
                path_parts.append(part)
        env["PATH"] = ":".join(path_parts)
        env["NPM_CONFIG_PREFIX"] = str(node_root)

    return McpServerSpec(name="tavily", command=command, args=args, env=env or None)


def resolve_tavily_search_tool_name(tool_names: list[str]) -> str | None:
    preferred = (
        "tavily-search",
        "tavily_search",
        "search",
    )
    lower_map = {name.lower(): name for name in tool_names}
    for cand in preferred:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    for name in tool_names:
        if "search" in name.lower():
            return name
    return None
