"""Gitea audit notify: append local audit log + shout via RepoAudit on Zulip."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from traceforge.config import TraceForgeSettings, get_settings
from traceforge.infrastructure.zulip.client import ZulipApiClient
from traceforge.interfaces.gitea.normalizer import GiteaAuditEvent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RepoAuditResult:
    notified: bool
    audit_path: str | None
    message: str
    zulip_message_id: int | None = None
    skipped_reason: str | None = None


class RepoAuditNotifier:
    def __init__(
        self,
        settings: TraceForgeSettings | None = None,
        *,
        zulip: ZulipApiClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.zulip = zulip or ZulipApiClient(self.settings)

    def handle(self, event: GiteaAuditEvent) -> RepoAuditResult:
        message = event.zulip_message()
        audit_path = self.write_audit(event, message=message)
        return self.notify_text(message, audit_path=audit_path)

    def write_audit(self, event: GiteaAuditEvent, *, message: str) -> Path | None:
        return self._append_audit_log(event, message=message)

    def notify_text(
        self,
        message: str,
        *,
        audit_path: Path | str | None = None,
        topic: str | None = None,
    ) -> RepoAuditResult:
        email = (self.settings.repoaudit_zulip_email or "").strip()
        api_key = (self.settings.repoaudit_zulip_api_key or "").strip()
        stream = (self.settings.repoaudit_notify_stream or "").strip()
        use_topic = (topic or self.settings.repoaudit_notify_topic or "").strip() or "gitea"

        if not email or not api_key:
            logger.warning("RepoAudit Zulip credentials missing; audit logged only")
            return RepoAuditResult(
                notified=False,
                audit_path=str(audit_path) if audit_path else None,
                message=message,
                skipped_reason="missing_repoaudit_credentials",
            )
        if not stream:
            return RepoAuditResult(
                notified=False,
                audit_path=str(audit_path) if audit_path else None,
                message=message,
                skipped_reason="missing_notify_stream",
            )

        try:
            self.zulip.ensure_stream_subscription(
                stream=stream,
                email=email,
                api_key=api_key,
            )
            mid = self.zulip.send_stream_message(
                stream=stream,
                topic=use_topic,
                content=message,
                email=email,
                api_key=api_key,
            )
        except Exception:
            logger.exception("Failed to notify Zulip via RepoAudit")
            raise

        return RepoAuditResult(
            notified=True,
            audit_path=str(audit_path) if audit_path else None,
            message=message,
            zulip_message_id=mid,
        )

    def _append_audit_log(self, event: GiteaAuditEvent, *, message: str) -> Path | None:
        try:
            db_path = Path(self.settings.traceforge_db_path).expanduser().resolve()
            audit_dir = db_path.parent / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            path = audit_dir / "gitea.jsonl"
            record: dict[str, Any] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event_type": event.event_type,
                "delivery_id": event.delivery_id,
                "repository": event.repository,
                "actor": event.actor,
                "summary": event.summary,
                "url": event.url,
                "message": message,
            }
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            return path
        except Exception:
            logger.exception("Failed to append Gitea audit log")
            return None
