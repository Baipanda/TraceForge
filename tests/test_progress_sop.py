"""progress-sop trigger parsing and Scope resolve smoke."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from traceforge.agent.models import AgentRequest, RunStatus
from traceforge.application.progress_sop import ProgressSopWorkflow, matches_progress_sop
from traceforge.application.todo_workflow import TodoWorkflow
from traceforge.config import get_settings
from traceforge.core.events import ActorRef, EventKind, EventSource, WorkspaceEvent, WorkspaceLocation
from traceforge.infrastructure.storage.sqlite_repository import SqliteTodoRepository


def test_matches_progress_sop() -> None:
    assert matches_progress_sop("@Jarvis 项目进度：todo-show")
    assert matches_progress_sop("sop continue run_id=abc window=7 include_audit=1 focus=blocked")
    assert not matches_progress_sop("随便聊聊")


def test_scope_resolves_todo_show_from_project_admin() -> None:
    settings = get_settings()
    repo = SqliteTodoRepository(Path(settings.traceforge_db_path))
    workflow = ProgressSopWorkflow(settings=settings, todo_workflow=TodoWorkflow(repo))
    event = WorkspaceEvent(
        event_id=str(uuid4()),
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id="1", display_name="Bai", email="bai@example.com"),
        location=WorkspaceLocation(
            workspace_id="default",
            channel_name="sandbox",
            topic="todo-show开发",
        ),
        payload={"text": "@Jarvis 项目进度：todo-show"},
        occurred_at=datetime.now(timezone.utc),
    )
    response = workflow.handle_request(AgentRequest(event=event, session_key="test:progress-sop"))
    assert response.status == RunStatus.SUCCEEDED
    assert response.run_id
    assert response.widget_content is not None
    assert any(item.get("type") == "project.resolve" and item.get("ok") for item in response.evidence)
    assert "Project Admin" in response.reply_text or "project_id" in response.reply_text
