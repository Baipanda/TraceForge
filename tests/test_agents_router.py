from __future__ import annotations

from pathlib import Path

from traceforge.agents import AgentRouter, load_agents_config
from traceforge.application.syntax_check import check_syntax, collect_changed_paths
from traceforge.core.events import (
    ActorRef,
    EventKind,
    EventSource,
    WorkspaceEvent,
    WorkspaceLocation,
)


def test_agents_yaml_routes() -> None:
    config = load_agents_config(Path(__file__).resolve().parents[1] / "agents.yaml")
    assert config.default_agent_id() == "main"
    router = AgentRouter(config)
    zulip = WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id="1"),
        location=WorkspaceLocation(workspace_id="2"),
        payload={},
    )
    gitea = WorkspaceEvent(
        source=EventSource.GITEA,
        kind=EventKind.REPOSITORY_UPDATED,
        actor=ActorRef(external_id="n"),
        location=WorkspaceLocation(workspace_id="gitea"),
        payload={},
    )
    assert router.resolve(zulip) == "main"
    assert router.resolve(gitea) == "gitea-audit"


def test_syntax_check_python() -> None:
    bad = check_syntax(path="a.py", content="def foo(\n")
    assert bad and bad[0].language == "python"
    assert check_syntax(path="b.py", content="x = 1\n") == []
    assert collect_changed_paths([{"added": ["a.py"], "modified": ["a.py"]}]) == ["a.py"]
