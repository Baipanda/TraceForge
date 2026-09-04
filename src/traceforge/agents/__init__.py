"""Multi-agent registry + binding router (OpenClaw-aligned)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from traceforge.core.events import EventSource, WorkspaceEvent


@dataclass(frozen=True)
class AgentEntry:
    agent_id: str
    workspace: str
    sessions: str
    default: bool = False
    tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class Binding:
    agent_id: str
    match: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentsConfig:
    agents: dict[str, AgentEntry]
    bindings: tuple[Binding, ...]
    shared_root: str = "workspace_shared"
    config_path: Path | None = None

    def default_agent_id(self) -> str:
        for agent_id, entry in self.agents.items():
            if entry.default:
                return agent_id
        if "main" in self.agents:
            return "main"
        if self.agents:
            return next(iter(self.agents))
        raise RuntimeError("no agents configured")

    def get(self, agent_id: str) -> AgentEntry:
        if agent_id not in self.agents:
            raise KeyError(f"unknown agentId: {agent_id}")
        return self.agents[agent_id]


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_agents_config_path() -> Path:
    raw = (__import__("os").environ.get("TRACEFORGE_AGENTS_CONFIG", "") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return project_root() / "agents.yaml"


def load_agents_config(path: Path | str | None = None) -> AgentsConfig:
    if path is None or str(path).strip() in {"", "."}:
        config_path = default_agents_config_path()
    else:
        config_path = Path(path)
    if not config_path.is_file():
        return _builtin_config(config_path if config_path.suffix else default_agents_config_path())
    raw = _parse_simple_yaml(config_path.read_text(encoding="utf-8"))
    return _from_dict(raw, config_path=config_path)


def resolve_workspace_root(entry: AgentEntry, *, repo_root: Path | None = None) -> Path:
    root = repo_root or project_root()
    workspace = Path(entry.workspace)
    if workspace.is_absolute():
        return workspace
    return (root / workspace).resolve()


def resolve_sessions_root(
    entry: AgentEntry,
    *,
    data_root: Path,
    legacy_sessions: Path | None = None,
) -> Path:
    """Resolve session directory; prefer agents/<id>/sessions, fall back to legacy flat sessions for main."""
    sessions = Path(entry.sessions)
    if sessions.is_absolute():
        path = sessions
    else:
        path = (data_root / sessions).resolve()
    if path.exists() or entry.agent_id != "main":
        path.mkdir(parents=True, exist_ok=True)
        return path
    if legacy_sessions and legacy_sessions.exists():
        return legacy_sessions
    path.mkdir(parents=True, exist_ok=True)
    return path


class AgentRouter:
    """Select agentId from WorkspaceEvent using bindings (specific first, AND fields)."""

    def __init__(self, config: AgentsConfig) -> None:
        self.config = config

    def resolve(self, event: WorkspaceEvent) -> str:
        channel = event.source.value
        delivery = event.payload.get("delivery") if isinstance(event.payload.get("delivery"), dict) else {}
        account = str(
            delivery.get("account")
            or delivery.get("email")
            or delivery.get("bot_email")
            or event.payload.get("delivery_account")
            or ""
        ).strip()
        bot_name = str(delivery.get("bot_name") or event.payload.get("delivery_bot_name") or "").strip()
        facts = {
            "channel": channel,
            "source": channel,
            "workspace_id": event.location.workspace_id or "",
            "project_id": event.location.project_id or "",
            "channel_id": event.location.channel_id or "",
            "channel_name": event.location.channel_name or "",
            "topic": event.location.topic or "",
            "account": account,
            "bot_name": bot_name,
        }
        # Prefer bindings that specify account/bot_name when those facts exist.
        for binding in self.config.bindings:
            if _match_all(binding.match, facts):
                return binding.agent_id
        return self.config.default_agent_id()


def _match_all(match: dict[str, str], facts: dict[str, str]) -> bool:
    if not match:
        return False
    for key, expected in match.items():
        actual = facts.get(key, "")
        if expected.endswith("*"):
            if not actual.startswith(expected[:-1]):
                return False
        elif actual != expected:
            return False
    return True


def _builtin_config(config_path: Path) -> AgentsConfig:
    return AgentsConfig(
        agents={
            "main": AgentEntry(
                agent_id="main",
                workspace="workspace",
                sessions="agents/main/sessions",
                default=True,
            ),
            "gitea-audit": AgentEntry(
                agent_id="gitea-audit",
                workspace="workspace-gitea-audit",
                sessions="agents/gitea-audit/sessions",
            ),
        },
        bindings=(
            Binding(agent_id="gitea-audit", match={"channel": "gitea"}),
            Binding(agent_id="main", match={"channel": "zulip"}),
        ),
        shared_root="workspace_shared",
        config_path=config_path,
    )


def _from_dict(raw: dict[str, Any], *, config_path: Path) -> AgentsConfig:
    agents_raw = raw.get("agents") or {}
    agents: dict[str, AgentEntry] = {}
    if isinstance(agents_raw, dict):
        for agent_id, spec in agents_raw.items():
            if not isinstance(spec, dict):
                continue
            tools = spec.get("tools") or []
            agents[str(agent_id)] = AgentEntry(
                agent_id=str(agent_id),
                workspace=str(spec.get("workspace") or f"workspace-{agent_id}"),
                sessions=str(spec.get("sessions") or f"agents/{agent_id}/sessions"),
                default=bool(spec.get("default", False)),
                tools=tuple(str(t) for t in tools) if isinstance(tools, list) else (),
            )
    bindings: list[Binding] = []
    for item in raw.get("bindings") or []:
        if not isinstance(item, dict):
            continue
        match = item.get("match") or {}
        if not isinstance(match, dict):
            match = {}
        agent_id = str(item.get("agentId") or item.get("agent_id") or "")
        if not agent_id:
            continue
        bindings.append(
            Binding(
                agent_id=agent_id,
                match={str(k): str(v) for k, v in match.items()},
            )
        )
    shared = raw.get("shared") or {}
    shared_root = "workspace_shared"
    if isinstance(shared, dict):
        shared_root = str(shared.get("root") or shared_root)
    if not agents:
        return _builtin_config(config_path)
    return AgentsConfig(
        agents=agents,
        bindings=tuple(bindings),
        shared_root=shared_root,
        config_path=config_path,
    )


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML subset parser for agents.yaml (no PyYAML dependency)."""
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return _parse_agents_yaml_fallback(text)


def _parse_agents_yaml_fallback(text: str) -> dict[str, Any]:
    """Indent-based parser covering agents / bindings / shared used by TraceForge."""
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))

    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    i = 0
    while i < len(lines):
        indent, content = lines[i]
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if content.startswith("- "):
            item_text = content[2:].strip()
            if not isinstance(parent, list):
                i += 1
                continue
            if ":" in item_text and not item_text.endswith(":"):
                key, value = item_text.split(":", 1)
                node: Any = {key.strip(): _scalar(value.strip())}
            elif item_text.endswith(":"):
                node = {item_text[:-1].strip(): {}}
            else:
                node = _scalar(item_text)
            parent.append(node)
            if isinstance(node, dict):
                stack.append((indent, node))
            i += 1
            continue

        if ":" in content:
            key, value = content.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                # Look ahead: list or map
                nxt = lines[i + 1] if i + 1 < len(lines) else None
                if nxt and nxt[0] > indent and nxt[1].startswith("- "):
                    child: Any = []
                else:
                    child = {}
                if isinstance(parent, dict):
                    parent[key] = child
                elif isinstance(parent, list) and parent and isinstance(parent[-1], dict):
                    parent[-1][key] = child
                stack.append((indent, child))
            else:
                if isinstance(parent, dict):
                    parent[key] = _scalar(value)
                elif isinstance(parent, list) and parent and isinstance(parent[-1], dict):
                    parent[-1][key] = _scalar(value)
        i += 1
    return root


def _scalar(value: str) -> Any:
    if value.lower() in {"true", "yes", "on"}:
        return True
    if value.lower() in {"false", "no", "off"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part.strip()) for part in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value
