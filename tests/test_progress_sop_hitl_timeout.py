"""HITL/zform timeout: cancel or default-branch degradation."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from traceforge.agent.models import AgentRequest, RunStatus
from traceforge.application.progress_sop import ProgressSopWorkflow, SopRunState, _deadline_iso
from traceforge.config import get_settings
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation


class _FakeProjectClient:
    def resolve(self, *, project_id: str) -> dict:
        return {
            "project_id": project_id,
            "display_name": "Todo Show",
            "zulip_stream": "sandbox",
            "zulip_topic": "todo-show开发",
            "docs_root": "workspace_shared/docs/todo-show",
            "subtree_code": "todo-show",
            "window_days": 7,
            "members": [],
        }

    def create_report(self, **kwargs):  # noqa: ANN003
        return {"ok": True}


class _FakeZulip:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def send_stream_message(self, **kwargs):  # noqa: ANN003
        self.messages.append(kwargs)
        return 1

    def fetch_topic_messages_all(self, *, stream: str, topic: str):
        return []


def _settings(**overrides):
    base = get_settings()
    return replace(base, **overrides)


def _event(text: str) -> WorkspaceEvent:
    return WorkspaceEvent(
        event_id=str(uuid4()),
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id="1", display_name="Bai", email="bai@example.com"),
        location=WorkspaceLocation(
            workspace_id="default",
            channel_name="sandbox",
            topic="todo-show开发",
        ),
        payload={"text": text},
        occurred_at=datetime.now(timezone.utc),
    )


def test_hitl_a_timeout_cancels(tmp_path: Path) -> None:
    settings = _settings(
        progress_sop_hitl_timeout_seconds=1,
        progress_sop_hitl_a_on_timeout="cancel",
    )
    zulip = _FakeZulip()
    workflow = ProgressSopWorkflow(
        settings=settings,
        project_client=_FakeProjectClient(),
        zulip_client=zulip,  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )
    started = workflow.handle_request(
        AgentRequest(event=_event("@Jarvis 项目进度：todo-show"), session_key="t")
    )
    assert started.run_id
    state = workflow._load(started.run_id)
    assert state is not None
    assert state.phase == "hitl_a"
    # Force deadline into the past.
    state.hitl_deadline_at = _deadline_iso(-5)
    # _deadline_iso with negative still adds seconds from now; write past ISO directly.
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.hitl_deadline_at = past
    workflow._save(state)

    outcomes = workflow.expire_due_runs(notify=True)
    assert outcomes
    assert outcomes[0]["action"] == "cancel"
    reloaded = workflow._load(started.run_id)
    assert reloaded is not None
    assert reloaded.phase == "cancelled"
    assert reloaded.timeout_resolved is True
    assert zulip.messages

    blocked = workflow.handle_request(
        AgentRequest(
            event=_event(
                f"@Jarvis sop continue run_id={started.run_id} window=7 include_audit=1 focus=blocked"
            ),
            session_key="t2",
        )
    )
    assert blocked.status == RunStatus.CANCELLED


def test_hitl_a_timeout_default_continues(tmp_path: Path) -> None:
    settings = _settings(
        progress_sop_hitl_timeout_seconds=1,
        progress_sop_hitl_a_on_timeout="default",
        progress_sop_hitl_b_on_timeout="cancel",
    )
    zulip = _FakeZulip()
    workflow = ProgressSopWorkflow(
        settings=settings,
        project_client=_FakeProjectClient(),
        zulip_client=zulip,  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )
    started = workflow.handle_request(
        AgentRequest(event=_event("@Jarvis 项目进度：todo-show"), session_key="t")
    )
    assert started.run_id
    state = workflow._load(started.run_id)
    assert state is not None
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.hitl_deadline_at = past
    workflow._save(state)

    outcomes = workflow.expire_due_runs(notify=True)
    assert outcomes
    assert outcomes[0]["action"] == "default"
    reloaded = workflow._load(started.run_id)
    assert reloaded is not None
    assert reloaded.phase == "hitl_b"
    assert reloaded.timeout_resolved is True
    assert reloaded.report_markdown
    assert zulip.messages


def test_hitl_b_timeout_ends_as_done(tmp_path: Path) -> None:
    settings = _settings(progress_sop_hitl_timeout_seconds=30, progress_sop_hitl_b_on_timeout="cancel")
    workflow = ProgressSopWorkflow(
        settings=settings,
        project_client=_FakeProjectClient(),
        zulip_client=_FakeZulip(),  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    state = SopRunState(
        run_id=str(uuid4()),
        project_id="todo-show",
        phase="hitl_b",
        created_at=now,
        updated_at=now,
        reply_stream="sandbox",
        reply_topic="todo-show开发",
        report_markdown="## report",
        hitl_deadline_at=(datetime.now(timezone.utc) - timedelta(seconds=2)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        hitl_timeout_action="cancel",
    )
    workflow._save(state)
    outcomes = workflow.expire_due_runs(notify=False)
    assert outcomes[0]["action"] == "cancel"
    reloaded = workflow._load(state.run_id)
    assert reloaded is not None
    assert reloaded.phase == "done"
