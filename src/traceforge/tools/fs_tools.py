"""Workspace filesystem tools (read-only by default; PathGuard enforced)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from traceforge.sandbox.path_guard import PathGuardError, resolve_under_root
from traceforge.sandbox.policy import SandboxPolicy, policy_from_settings
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry

_SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".traceforge",
    ".pytest_cache",
    ".mypy_cache",
}


def register_fs_tools(
    registry: ToolRegistry,
    *,
    policy: SandboxPolicy | None = None,
) -> None:
    policy = policy or policy_from_settings()

    read_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path under the agent workspace (e.g. AGENTS.md, skills/todo-create/SKILL.md).",
            },
        },
        "required": ["path"],
    }
    grep_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Substring to search for (case-insensitive)."},
            "path": {
                "type": "string",
                "description": "Optional subdirectory or file under the workspace to limit search.",
            },
            "glob": {
                "type": "string",
                "description": "Optional filename suffix filter, e.g. .md or .py",
            },
            "max_matches": {"type": "integer", "description": "Max matching lines to return."},
        },
        "required": ["query"],
    }

    registry.register(
        RegisteredTool(
            name="fs.read",
            description=(
                "Read a text file inside the agent workspace (sandbox PathGuard). "
                "Use for AGENTS.md, skills, memory notes, or other workspace files."
            ),
            schema=read_schema,
            handler=lambda arguments: _fs_read(arguments, policy),
        )
    )
    registry.register(
        RegisteredTool(
            name="fs.grep",
            description=(
                "Search text files under the agent workspace for a substring (sandbox PathGuard). "
                "Use when you do not know the exact file path."
            ),
            schema=grep_schema,
            handler=lambda arguments: _fs_grep(arguments, policy),
        )
    )


def _policy_denied(tool_name: str, reason: str) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        ok=False,
        error=reason,
        evidence=[{"type": "policy_denied", "tool_name": tool_name, "reason": reason}],
    )


def _fs_read(arguments: dict[str, Any], policy: SandboxPolicy) -> ToolResult:
    if not policy.allows_read():
        return _policy_denied("fs.read", policy.deny_reason("fs.read") or "read blocked")

    path_arg = str(arguments.get("path") or "").strip()
    try:
        target = resolve_under_root(policy.workspace_root, path_arg, must_exist=True)
    except PathGuardError as exc:
        return ToolResult(
            tool_name="fs.read",
            ok=False,
            error=exc.message,
            evidence=[{"type": "policy_denied", "code": exc.code, "path": path_arg}],
        )

    if not target.is_file():
        return ToolResult(
            tool_name="fs.read",
            ok=False,
            error=f"not a file: {path_arg}",
            evidence=[{"type": "fs.read", "status": "not_a_file", "path": path_arg}],
        )

    size = target.stat().st_size
    truncated = size > policy.max_read_bytes
    try:
        raw = target.read_bytes()[: policy.max_read_bytes]
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ToolResult(
            tool_name="fs.read",
            ok=False,
            error=f"file is not valid UTF-8 text: {path_arg}",
            evidence=[{"type": "fs.read", "status": "binary_or_invalid", "path": path_arg}],
        )

    rel = _rel(policy.workspace_root, target)
    reply = f"已读取 `{rel}`（{len(text)} 字符"
    if truncated:
        reply += f"，已截断至 {policy.max_read_bytes} 字节"
    reply += "）。"
    return ToolResult(
        tool_name="fs.read",
        ok=True,
        data={
            "path": rel,
            "content": text,
            "bytes_read": len(raw),
            "truncated": truncated,
            "reply_text": reply,
        },
        evidence=[
            {
                "type": "fs.read",
                "path": rel,
                "bytes_read": len(raw),
                "truncated": truncated,
            }
        ],
    )


def _fs_grep(arguments: dict[str, Any], policy: SandboxPolicy) -> ToolResult:
    if not policy.allows_read():
        return _policy_denied("fs.grep", policy.deny_reason("fs.grep") or "read blocked")

    query = str(arguments.get("query") or "").strip()
    if not query:
        return ToolResult(tool_name="fs.grep", ok=False, error="query is required")

    path_arg = str(arguments.get("path") or "").strip() or "."
    suffix = str(arguments.get("glob") or "").strip()
    if suffix and not suffix.startswith("."):
        # treat ".md" or "md" or "*.md" loosely as suffix
        suffix = "." + suffix.lstrip("*.")

    max_matches = arguments.get("max_matches")
    try:
        limit = int(max_matches) if max_matches is not None else policy.grep_max_matches
    except (TypeError, ValueError):
        limit = policy.grep_max_matches
    limit = max(1, min(limit, 200))

    try:
        start = resolve_under_root(policy.workspace_root, path_arg, must_exist=True)
    except PathGuardError as exc:
        return ToolResult(
            tool_name="fs.grep",
            ok=False,
            error=exc.message,
            evidence=[{"type": "policy_denied", "code": exc.code, "path": path_arg}],
        )

    needle = query.lower()
    matches: list[dict[str, Any]] = []
    files_scanned = 0
    truncated = False

    files = _iter_files(start, suffix=suffix)
    for file_path in files:
        if len(matches) >= limit:
            truncated = True
            break
        try:
            if file_path.stat().st_size > policy.grep_max_file_bytes:
                continue
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        files_scanned += 1
        rel = _rel(policy.workspace_root, file_path)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if needle in line.lower():
                matches.append(
                    {
                        "path": rel,
                        "line": line_no,
                        "text": line.strip()[:240],
                    }
                )
                if len(matches) >= limit:
                    truncated = True
                    break

    reply_lines = [f"在 workspace 中搜索 `{query}`：{len(matches)} 条匹配（扫描 {files_scanned} 个文件）。"]
    for item in matches[:15]:
        reply_lines.append(f"- `{item['path']}:{item['line']}` {item['text']}")
    if truncated or len(matches) > 15:
        reply_lines.append("（结果已截断，可缩小 path/glob 再搜。）")

    return ToolResult(
        tool_name="fs.grep",
        ok=True,
        data={
            "query": query,
            "path": path_arg,
            "matches": matches,
            "files_scanned": files_scanned,
            "truncated": truncated,
            "reply_text": "\n".join(reply_lines),
        },
        evidence=[
            {
                "type": "fs.grep",
                "query": query,
                "match_count": len(matches),
                "files_scanned": files_scanned,
                "truncated": truncated,
            }
        ],
    )


def _iter_files(start: Path, *, suffix: str) -> list[Path]:
    if start.is_file():
        if suffix and start.suffix != suffix:
            return []
        return [start]

    results: list[Path] = []
    for path in sorted(start.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        if suffix and path.suffix != suffix:
            continue
        results.append(path)
    return results


def _rel(root: Path, target: Path) -> str:
    try:
        return str(target.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(target)
