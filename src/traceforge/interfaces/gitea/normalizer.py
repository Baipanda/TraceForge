"""Normalize Gitea webhook payloads into a small audit summary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GiteaAuditEvent:
    """Minimal structured view of a Gitea webhook for notify + audit log."""

    event_type: str
    delivery_id: str | None
    repository: str
    actor: str
    summary: str
    detail_lines: tuple[str, ...] = ()
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def zulip_message(self) -> str:
        lines = [f"**[Gitea]** {self.summary}"]
        for line in self.detail_lines[:8]:
            lines.append(f"- {line}")
        if self.url:
            lines.append(f"\n{self.url}")
        return "\n".join(lines)


def normalize_gitea_webhook(
    payload: dict[str, Any],
    *,
    event_type: str | None = None,
    delivery_id: str | None = None,
) -> GiteaAuditEvent | None:
    """Parse common Gitea events. Returns None for ignored/unknown types (e.g. ping handled upstream)."""
    event = (event_type or "").strip().lower() or _infer_event_type(payload)
    if event in {"", "ping"}:
        return None

    repo = _repo_name(payload)
    if event == "push":
        return _normalize_push(payload, delivery_id=delivery_id, repository=repo)
    if event in {"pull_request", "pullrequest"}:
        return _normalize_pull_request(payload, delivery_id=delivery_id, repository=repo)
    if event == "issues":
        return _normalize_issues(payload, delivery_id=delivery_id, repository=repo)
    if event == "create":
        return _normalize_create(payload, delivery_id=delivery_id, repository=repo)
    if event == "delete":
        return _normalize_delete(payload, delivery_id=delivery_id, repository=repo)

    actor = _actor_name(payload)
    return GiteaAuditEvent(
        event_type=event or "unknown",
        delivery_id=delivery_id,
        repository=repo,
        actor=actor,
        summary=f"{actor} triggered `{event or 'unknown'}` on `{repo}`",
        url=_html_url(payload),
        raw=payload,
    )


def _normalize_push(
    payload: dict[str, Any], *, delivery_id: str | None, repository: str
) -> GiteaAuditEvent:
    actor = _actor_name(payload, preferred_keys=("pusher", "sender"))
    ref = str(payload.get("ref") or "")
    branch = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else ref
    commits = payload.get("commits") if isinstance(payload.get("commits"), list) else []
    details: list[str] = []
    for commit in commits[:5]:
        if not isinstance(commit, dict):
            continue
        sha = str(commit.get("id") or "")[:7]
        msg = str(commit.get("message") or "").strip().splitlines()[0] if commit.get("message") else ""
        if sha or msg:
            details.append(f"`{sha}` {msg}".strip())
    total = len(commits)
    if total > 5:
        details.append(f"… and {total - 5} more")
    summary = f"{actor} pushed to `{repository}` on `{branch or 'unknown'}` ({total} commit{'s' if total != 1 else ''})"
    url = str(payload.get("compare_url") or "") or _html_url(payload)
    return GiteaAuditEvent(
        event_type="push",
        delivery_id=delivery_id,
        repository=repository,
        actor=actor,
        summary=summary,
        detail_lines=tuple(details),
        url=url or None,
        raw=payload,
    )


def _normalize_pull_request(
    payload: dict[str, Any], *, delivery_id: str | None, repository: str
) -> GiteaAuditEvent:
    action = str(payload.get("action") or "updated")
    pr = payload.get("pull_request") if isinstance(payload.get("pull_request"), dict) else {}
    actor = _actor_name(payload)
    number = pr.get("number") or payload.get("number") or "?"
    title = str(pr.get("title") or "").strip() or "(no title)"
    summary = f"{actor} {action} PR #{number} on `{repository}`: {title}"
    url = str(pr.get("html_url") or "") or _html_url(payload)
    return GiteaAuditEvent(
        event_type="pull_request",
        delivery_id=delivery_id,
        repository=repository,
        actor=actor,
        summary=summary,
        url=url or None,
        raw=payload,
    )


def _normalize_issues(
    payload: dict[str, Any], *, delivery_id: str | None, repository: str
) -> GiteaAuditEvent:
    action = str(payload.get("action") or "updated")
    issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
    actor = _actor_name(payload)
    number = issue.get("number") or "?"
    title = str(issue.get("title") or "").strip() or "(no title)"
    summary = f"{actor} {action} issue #{number} on `{repository}`: {title}"
    url = str(issue.get("html_url") or "") or _html_url(payload)
    return GiteaAuditEvent(
        event_type="issues",
        delivery_id=delivery_id,
        repository=repository,
        actor=actor,
        summary=summary,
        url=url or None,
        raw=payload,
    )


def _normalize_create(
    payload: dict[str, Any], *, delivery_id: str | None, repository: str
) -> GiteaAuditEvent:
    actor = _actor_name(payload)
    ref_type = str(payload.get("ref_type") or "ref")
    ref = str(payload.get("ref") or "")
    summary = f"{actor} created {ref_type} `{ref}` on `{repository}`"
    return GiteaAuditEvent(
        event_type="create",
        delivery_id=delivery_id,
        repository=repository,
        actor=actor,
        summary=summary,
        url=_html_url(payload),
        raw=payload,
    )


def _normalize_delete(
    payload: dict[str, Any], *, delivery_id: str | None, repository: str
) -> GiteaAuditEvent:
    actor = _actor_name(payload)
    ref_type = str(payload.get("ref_type") or "ref")
    ref = str(payload.get("ref") or "")
    summary = f"{actor} deleted {ref_type} `{ref}` on `{repository}`"
    return GiteaAuditEvent(
        event_type="delete",
        delivery_id=delivery_id,
        repository=repository,
        actor=actor,
        summary=summary,
        url=_html_url(payload),
        raw=payload,
    )


def _infer_event_type(payload: dict[str, Any]) -> str:
    if "commits" in payload and "ref" in payload:
        return "push"
    if "pull_request" in payload:
        return "pull_request"
    if "issue" in payload and "pull_request" not in payload:
        return "issues"
    return ""


def _repo_name(payload: dict[str, Any]) -> str:
    repo = payload.get("repository")
    if isinstance(repo, dict):
        full = str(repo.get("full_name") or "").strip()
        if full:
            return full
        name = str(repo.get("name") or "").strip()
        owner = repo.get("owner")
        if isinstance(owner, dict):
            login = str(owner.get("login") or owner.get("username") or "").strip()
            if login and name:
                return f"{login}/{name}"
        if name:
            return name
    return "unknown/repo"


def _actor_name(payload: dict[str, Any], preferred_keys: tuple[str, ...] = ("sender", "pusher")) -> str:
    for key in preferred_keys:
        person = payload.get(key)
        if isinstance(person, dict):
            for field_name in ("full_name", "username", "login", "email"):
                value = str(person.get(field_name) or "").strip()
                if value:
                    return value
    return "someone"


def _html_url(payload: dict[str, Any]) -> str | None:
    repo = payload.get("repository")
    if isinstance(repo, dict):
        url = str(repo.get("html_url") or "").strip()
        if url:
            return url
    return None
