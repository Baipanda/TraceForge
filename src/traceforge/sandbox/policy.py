"""Sandbox policy: workspace access and tool allow/deny."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from traceforge.config import TraceForgeSettings


DEFAULT_DENIED_TOOLS = frozenset({"fs.write", "fs.edit", "exec", "apply_patch"})


@dataclass(frozen=True)
class SandboxPolicy:
    """Logical sandbox posture for agent tools.

    Stage-1 only: no container runtime. Enforcement is PathGuard + tool deny.
    """

    workspace_root: Path
    workspace_access: str = "ro"  # none | ro | rw
    denied_tools: frozenset[str] = DEFAULT_DENIED_TOOLS
    max_read_bytes: int = 200_000
    grep_max_matches: int = 50
    grep_max_file_bytes: int = 1_000_000

    def allows_tool(self, name: str) -> bool:
        if name in self.denied_tools:
            return False
        if name.startswith("fs.") and self.workspace_access == "none":
            return False
        if name in {"fs.write", "fs.edit", "apply_patch"} and self.workspace_access != "rw":
            return False
        return True

    def allows_read(self) -> bool:
        return self.workspace_access in {"ro", "rw"}

    def allows_write(self) -> bool:
        return self.workspace_access == "rw"

    def deny_reason(self, name: str) -> str | None:
        if self.allows_tool(name):
            return None
        if name in self.denied_tools:
            return f"tool denied by sandbox policy: {name}"
        if name.startswith("fs.") and self.workspace_access == "none":
            return "workspace_access=none blocks filesystem tools"
        if name in {"fs.write", "fs.edit", "apply_patch"}:
            return f"workspace_access={self.workspace_access} blocks write tools"
        return f"tool not allowed: {name}"


def default_workspace_root() -> Path:
    # src/traceforge/sandbox/policy.py -> TraceForge repo root / workspace
    return Path(__file__).resolve().parents[3] / "workspace"


def policy_from_settings(settings: TraceForgeSettings | None = None) -> SandboxPolicy:
    if settings is None:
        from traceforge.config import get_settings

        settings = get_settings()

    root_raw = (settings.sandbox_workspace_root or "").strip()
    root = Path(root_raw).expanduser() if root_raw else default_workspace_root()
    root = root.resolve()

    access = (settings.sandbox_workspace_access or "ro").strip().lower()
    if access not in {"none", "ro", "rw"}:
        access = "ro"

    denied_raw = (settings.sandbox_denied_tools or "").strip()
    if denied_raw:
        denied = frozenset(part.strip() for part in denied_raw.split(",") if part.strip())
    else:
        denied = DEFAULT_DENIED_TOOLS

    return SandboxPolicy(
        workspace_root=root,
        workspace_access=access,
        denied_tools=denied,
        max_read_bytes=max(1024, int(settings.sandbox_max_read_bytes)),
        grep_max_matches=max(1, int(settings.sandbox_grep_max_matches)),
        grep_max_file_bytes=max(1024, int(settings.sandbox_grep_max_file_bytes)),
    )
