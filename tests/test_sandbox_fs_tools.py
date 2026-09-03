from __future__ import annotations

from pathlib import Path

import pytest

from traceforge.sandbox.path_guard import PathGuardError, resolve_under_root
from traceforge.sandbox.policy import SandboxPolicy
from traceforge.tools.fs_tools import register_fs_tools
from traceforge.tools.models import ToolCall
from traceforge.tools.registry import ToolRegistry


def test_path_guard_allows_relative_under_root(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("hello", encoding="utf-8")
    resolved = resolve_under_root(tmp_path, "AGENTS.md", must_exist=True)
    assert resolved == (tmp_path / "AGENTS.md").resolve()


def test_path_guard_rejects_parent_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(PathGuardError) as exc:
        resolve_under_root(tmp_path, "../secret.txt")
    assert exc.value.code == "path_escape"


def test_path_guard_rejects_absolute_outside(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(PathGuardError) as exc:
        resolve_under_root(tmp_path, str(outside))
    assert exc.value.code == "path_escape"


def test_path_guard_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "linked-secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "escape.txt"
    link.symlink_to(outside)
    with pytest.raises(PathGuardError) as exc:
        resolve_under_root(tmp_path, "escape.txt")
    assert exc.value.code == "path_escape"


def test_fs_read_and_grep_under_policy(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("alpha beta gamma\nsecond line beta\n", encoding="utf-8")
    policy = SandboxPolicy(workspace_root=tmp_path, workspace_access="ro")
    registry = ToolRegistry(policy=policy)
    register_fs_tools(registry, policy=policy)

    read = registry.call(ToolCall(name="fs.read", arguments={"path": "notes.md"}))
    assert read.ok
    assert "alpha beta" in read.data["content"]

    grep = registry.call(ToolCall(name="fs.grep", arguments={"query": "beta"}))
    assert grep.ok
    assert len(grep.data["matches"]) == 2
    assert all(m["path"] == "notes.md" for m in grep.data["matches"])


def test_fs_read_denied_when_access_none(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    policy = SandboxPolicy(workspace_root=tmp_path, workspace_access="none")
    registry = ToolRegistry(policy=policy)
    register_fs_tools(registry, policy=policy)

    names = {item["name"] for item in registry.list_schemas()}
    assert "fs.read" not in names
    assert "fs.grep" not in names

    result = registry.call(ToolCall(name="fs.read", arguments={"path": "a.md"}))
    assert not result.ok
    assert result.evidence[0]["type"] == "policy_denied"


def test_registry_hides_explicitly_denied_tools(tmp_path: Path) -> None:
    policy = SandboxPolicy(
        workspace_root=tmp_path,
        workspace_access="ro",
        denied_tools=frozenset({"fs.grep", "exec"}),
    )
    registry = ToolRegistry(policy=policy)
    register_fs_tools(registry, policy=policy)
    names = {item["name"] for item in registry.list_schemas()}
    assert "fs.read" in names
    assert "fs.grep" not in names
