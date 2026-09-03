"""gitea-audit agent: webhook → audit + light syntax review → Zulip (RepoAudit)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from traceforge.agents import (
    AgentRouter,
    AgentsConfig,
    load_agents_config,
    resolve_sessions_root,
    resolve_workspace_root,
)
from traceforge.application.repo_audit import RepoAuditNotifier, RepoAuditResult
from traceforge.application.syntax_check import (
    check_syntax,
    collect_changed_paths,
    format_findings_markdown,
    language_for_path,
)
from traceforge.config import TraceForgeSettings, get_settings
from traceforge.core.events import (
    ActorRef,
    EventKind,
    EventSource,
    WorkspaceEvent,
    WorkspaceLocation,
)
from traceforge.infrastructure.gitea.client import GiteaApiClient
from traceforge.interfaces.gitea.normalizer import GiteaAuditEvent
from traceforge.session.transcript import JsonlSessionStore, SessionEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GiteaAuditAgentResult:
    agent_id: str
    session_key: str
    notify: RepoAuditResult
    findings_count: int
    checked_files: int
    analysis_markdown: str


class GiteaAuditAgent:
    """Dedicated handler for Gitea channel (binding → gitea-audit)."""

    AGENT_ID = "gitea-audit"

    def __init__(
        self,
        settings: TraceForgeSettings | None = None,
        *,
        agents_config: AgentsConfig | None = None,
        notifier: RepoAuditNotifier | None = None,
        gitea: GiteaApiClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.agents_config = agents_config or load_agents_config()
        self.router = AgentRouter(self.agents_config)
        self.notifier = notifier or RepoAuditNotifier(self.settings)
        self.gitea = gitea or GiteaApiClient(self.settings)
        entry = self.agents_config.get(self.AGENT_ID)
        data_root = Path(self.settings.traceforge_db_path).expanduser().resolve().parent
        self.workspace_root = resolve_workspace_root(entry)
        self.session_store = JsonlSessionStore(
            resolve_sessions_root(entry, data_root=data_root)
        )

    def handle(
        self,
        audit_event: GiteaAuditEvent,
        *,
        raw_payload: dict[str, Any],
    ) -> GiteaAuditAgentResult:
        workspace_event = to_workspace_event(audit_event, raw_payload=raw_payload)
        agent_id = self.router.resolve(workspace_event)
        if agent_id != self.AGENT_ID:
            logger.warning("expected gitea-audit binding, got %s", agent_id)

        session_key = gitea_session_key(audit_event, raw_payload=raw_payload)
        analysis = ""
        findings_count = 0
        checked = 0
        if audit_event.event_type == "push":
            analysis, findings_count, checked = self._analyze_push(raw_payload)

        shout = audit_event.zulip_message()
        if analysis:
            message = f"{shout}\n\n---\n**gitea-audit**\n{analysis}"
        else:
            message = shout

        self.session_store.append(
            session_key,
            SessionEvent(
                type="user",
                content=shout,
                person_id=workspace_event.actor.person_id,
            ),
        )
        audit_path = self.notifier.write_audit(audit_event, message=message)
        notify = self.notifier.notify_text(message, audit_path=audit_path)
        self.session_store.append(
            session_key,
            SessionEvent(type="assistant", content=message),
        )
        # Also mirror into agent memory daily if workspace exists
        self._append_daily_note(audit_event, findings_count=findings_count)

        return GiteaAuditAgentResult(
            agent_id=self.AGENT_ID,
            session_key=session_key,
            notify=notify,
            findings_count=findings_count,
            checked_files=checked,
            analysis_markdown=analysis,
        )

    def _analyze_push(self, payload: dict[str, Any]) -> tuple[str, int, int]:
        commits = payload.get("commits") if isinstance(payload.get("commits"), list) else []
        paths = collect_changed_paths(commits)
        ref = str(payload.get("after") or payload.get("ref") or "").strip()
        owner, repo = _split_repo(payload)
        findings = []
        checked = 0
        skipped: list[str] = []

        checkable = [p for p in paths if language_for_path(p)]
        others = [p for p in paths if not language_for_path(p)]
        skipped.extend(others)

        if not checkable:
            md = format_findings_markdown([], checked=0, skipped=skipped or paths)
            return md, 0, 0

        if not self.gitea.enabled:
            skipped.extend(checkable)
            md = (
                "语法检查跳过：未配置 `TRACEFORGE_GITEA_URL` / `TRACEFORGE_GITEA_TOKEN`，"
                "无法拉取文件内容。\n"
                + format_findings_markdown([], checked=0, skipped=skipped)
            )
            return md, 0, 0

        for path in checkable[:30]:
            file_obj = self.gitea.fetch_raw_file(owner=owner, repo=repo, path=path, ref=ref)
            if file_obj is None:
                skipped.append(path)
                continue
            checked += 1
            findings.extend(check_syntax(path=path, content=file_obj.content))

        return format_findings_markdown(findings, checked=checked, skipped=skipped), len(findings), checked

    def _append_daily_note(self, event: GiteaAuditEvent, *, findings_count: int) -> None:
        memory_dir = self.workspace_root / "memory"
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
            from datetime import datetime, timezone

            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            path = memory_dir / f"{day}.md"
            line = (
                f"- `{event.event_type}` {event.repository} by {event.actor}"
                f" — syntax_findings={findings_count}\n"
            )
            if not path.exists():
                path.write_text(f"# gitea-audit {day}\n\n{line}", encoding="utf-8")
            else:
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
        except Exception:
            logger.exception("failed to append gitea-audit daily note")


def to_workspace_event(
    audit_event: GiteaAuditEvent,
    *,
    raw_payload: dict[str, Any],
) -> WorkspaceEvent:
    owner, repo = _split_repo(raw_payload)
    ref = str(raw_payload.get("ref") or "")
    return WorkspaceEvent(
        source=EventSource.GITEA,
        kind=EventKind.REPOSITORY_UPDATED,
        actor=ActorRef(
            external_id=audit_event.actor,
            display_name=audit_event.actor,
        ),
        location=WorkspaceLocation(
            workspace_id="gitea",
            project_id=audit_event.repository,
            channel_id=f"{owner}/{repo}" if owner else audit_event.repository,
            channel_name=audit_event.repository,
            topic=ref or audit_event.event_type,
        ),
        payload={
            "text": audit_event.zulip_message(),
            "gitea_event_type": audit_event.event_type,
            "raw": raw_payload,
        },
        external_event_id=audit_event.delivery_id,
    )


def gitea_session_key(audit_event: GiteaAuditEvent, *, raw_payload: dict[str, Any]) -> str:
    ref = str(raw_payload.get("ref") or audit_event.event_type or "_")
    return (
        f"agent:gitea-audit:gitea:"
        f"{quote(audit_event.repository, safe='')}"
        f":{quote(ref, safe='')}"
    )


def _split_repo(payload: dict[str, Any]) -> tuple[str, str]:
    repo = payload.get("repository")
    if isinstance(repo, dict):
        full = str(repo.get("full_name") or "").strip()
        if "/" in full:
            owner, name = full.split("/", 1)
            return owner, name
        name = str(repo.get("name") or "").strip()
        owner_obj = repo.get("owner")
        if isinstance(owner_obj, dict):
            login = str(owner_obj.get("login") or owner_obj.get("username") or "").strip()
            if login and name:
                return login, name
        if name:
            return "", name
    return "", "unknown"
