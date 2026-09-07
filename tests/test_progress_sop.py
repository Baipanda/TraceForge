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


def test_scope_resolves_todo_show_from_project_admin(tmp_path) -> None:
    settings = get_settings()
    repo = SqliteTodoRepository(Path(settings.traceforge_db_path))
    workflow = ProgressSopWorkflow(
        settings=settings,
        todo_workflow=TodoWorkflow(repo),
        runs_dir=tmp_path / "sop_runs",
    )
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
    choices = response.widget_content["extra_data"]["choices"]
    assert [c["short_name"] for c in choices] == [
        "1. 窗口 7 天，含 RepoAudit（推荐默认）",
        "2. 窗口 14 天，含 RepoAudit（偏文档对齐）",
        "3. 窗口 7 天，跳过 Audit（更快出报告）",
    ]
    assert all(c.get("long_name", "") == "" for c in choices)
    assert all(c["reply"].endswith(f"选择 {i}") for i, c in enumerate(choices, start=1))
    assert "```" not in response.reply_text
    assert "请在下方选择框" not in response.reply_text
    assert "HITL-A" not in response.reply_text
    assert any(item.get("type") == "project.resolve" and item.get("ok") for item in response.evidence)
    assert "Project Admin" in response.reply_text or "project_id" in response.reply_text


def test_hitl_choice_resolves_waiting_run(tmp_path) -> None:
    settings = get_settings()
    repo = SqliteTodoRepository(Path(settings.traceforge_db_path))
    workflow = ProgressSopWorkflow(
        settings=settings,
        todo_workflow=TodoWorkflow(repo),
        runs_dir=tmp_path / "sop_runs",
    )
    start_event = WorkspaceEvent(
        event_id=str(uuid4()),
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id="1", display_name="Bai", email="bai@example.com"),
        location=WorkspaceLocation(
            workspace_id="default",
            channel_name="sandbox",
            topic="choice-test",
        ),
        payload={"text": "@Jarvis 项目进度：todo-show"},
        occurred_at=datetime.now(timezone.utc),
    )
    started = workflow.handle_request(AgentRequest(event=start_event, session_key="t1"))
    assert started.run_id
    # Option 3: skip audit
    choice_event = WorkspaceEvent(
        event_id=str(uuid4()),
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(external_id="1", display_name="Bai", email="bai@example.com"),
        location=WorkspaceLocation(
            workspace_id="default",
            channel_name="sandbox",
            topic="choice-test",
        ),
        payload={"text": "@Jarvis 选择 3"},
        occurred_at=datetime.now(timezone.utc),
    )
    continued = workflow.handle_request(AgentRequest(event=choice_event, session_key="t2"))
    assert continued.status == RunStatus.SUCCEEDED
    assert continued.run_id == started.run_id
    assert continued.widget_content is not None
    assert "请在下方选择框" not in continued.reply_text
    assert continued.widget_content["extra_data"]["choices"][0]["reply"].endswith("选择 1")


def test_audit_posts_repoaudit_zulip_summary(tmp_path) -> None:
    class FakeZulip:
        def __init__(self) -> None:
            self.posts: list[dict] = []

        def send_stream_message(self, **kwargs):  # noqa: ANN003
            self.posts.append(kwargs)
            return 99

        def fetch_topic_messages_all(self, *, stream: str, topic: str):
            return []

    settings = get_settings()
    zulip = FakeZulip()
    workflow = ProgressSopWorkflow(
        settings=settings,
        todo_workflow=TodoWorkflow(SqliteTodoRepository(Path(settings.traceforge_db_path))),
        zulip_client=zulip,  # type: ignore[arg-type]
        runs_dir=tmp_path / "sop_runs",
    )
    start = workflow.handle_request(
        AgentRequest(
            event=WorkspaceEvent(
                event_id=str(uuid4()),
                source=EventSource.ZULIP,
                kind=EventKind.MESSAGE_CREATED,
                actor=ActorRef(external_id="1", display_name="Bai", email="bai@example.com"),
                location=WorkspaceLocation(
                    workspace_id="default",
                    channel_name="sandbox",
                    topic="audit-notify",
                ),
                payload={"text": "@Jarvis 项目进度：todo-show"},
                occurred_at=datetime.now(timezone.utc),
            ),
            session_key="a1",
        )
    )
    assert start.run_id
    continued = workflow.handle_request(
        AgentRequest(
            event=WorkspaceEvent(
                event_id=str(uuid4()),
                source=EventSource.ZULIP,
                kind=EventKind.MESSAGE_CREATED,
                actor=ActorRef(external_id="1", display_name="Bai", email="bai@example.com"),
                location=WorkspaceLocation(
                    workspace_id="default",
                    channel_name="sandbox",
                    topic="audit-notify",
                ),
                payload={"text": "@Jarvis 选择 1"},
                occurred_at=datetime.now(timezone.utc),
            ),
            session_key="a2",
        )
    )
    assert continued.status == RunStatus.SUCCEEDED
    assert any(p.get("email") == settings.repoaudit_zulip_email for p in zulip.posts) or any(
        "RepoAudit" in str(p.get("content") or "") for p in zulip.posts
    )
    assert any("审查" in str(p.get("content") or "") or "RepoAudit" in str(p.get("content") or "") for p in zulip.posts)
    repo_posts = [p for p in zulip.posts if p.get("email") == settings.repoaudit_zulip_email]
    assert repo_posts
    assert repo_posts[0]["stream"] == "sandbox"
    assert repo_posts[0]["topic"] == "audit-notify"
