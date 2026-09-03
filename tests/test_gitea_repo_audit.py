from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from traceforge.application.repo_audit import RepoAuditNotifier
from traceforge.config import TraceForgeSettings
from traceforge.interfaces.gitea.normalizer import normalize_gitea_webhook
from traceforge.interfaces.gitea.signature import verify_gitea_signature


def test_verify_gitea_signature_roundtrip() -> None:
    body = b'{"ref":"refs/heads/main"}'
    secret = "s3cret"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_gitea_signature(body=body, secret=secret, signature_header=sig)
    assert verify_gitea_signature(body=body, secret=secret, signature_header=f"sha256={sig}")
    assert not verify_gitea_signature(body=body, secret=secret, signature_header="deadbeef")
    assert verify_gitea_signature(body=body, secret="", signature_header=None)


def test_normalize_push_summary() -> None:
    event = normalize_gitea_webhook(
        {
            "ref": "refs/heads/main",
            "compare_url": "http://gitea/compare/a...b",
            "pusher": {"login": "neymar", "full_name": "Neymar"},
            "repository": {"full_name": "TraceForge/demo"},
            "commits": [
                {"id": "abcdef012345", "message": "fix login\n\nbody"},
                {"id": "111122223333", "message": "add tests"},
            ],
        },
        event_type="push",
        delivery_id="d1",
    )
    assert event is not None
    assert event.event_type == "push"
    assert event.repository == "TraceForge/demo"
    assert "Neymar" in event.summary
    assert "main" in event.summary
    assert "2 commit" in event.summary
    assert event.detail_lines[0].startswith("`abcdef0`")
    text = event.zulip_message()
    assert text.startswith("**[Gitea]**")
    assert "http://gitea/compare/a...b" in text


def test_normalize_pull_request() -> None:
    event = normalize_gitea_webhook(
        {
            "action": "opened",
            "sender": {"login": "peter"},
            "repository": {"full_name": "TraceForge/demo"},
            "pull_request": {
                "number": 7,
                "title": "Wire audit",
                "html_url": "http://gitea/pr/7",
            },
        },
        event_type="pull_request",
    )
    assert event is not None
    assert "PR #7" in event.summary
    assert "opened" in event.summary


def test_repo_audit_writes_jsonl_without_credentials(tmp_path: Path) -> None:
    settings = TraceForgeSettings(
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        traceforge_api_url="http://127.0.0.1:19090",
        traceforge_db_path=str(tmp_path / "db.sqlite3"),
        zulip_url="https://127.0.0.1:18443",
        zulip_email="Jarvis-bot@traceforge.local",
        zulip_api_key="",
        zulip_bot_name="Jarvis",
        zulip_verify_ssl=False,
        zulip_poll_interval_seconds=1.0,
        repoaudit_zulip_email="RepoAudit-bot@traceforge.local",
        repoaudit_zulip_api_key="",
        repoaudit_notify_stream="general",
        repoaudit_notify_topic="gitea",
    )
    event = normalize_gitea_webhook(
        {
            "ref": "refs/heads/main",
            "pusher": {"login": "neymar"},
            "repository": {"full_name": "TraceForge/demo"},
            "commits": [{"id": "abc", "message": "hi"}],
        },
        event_type="push",
    )
    assert event is not None
    result = RepoAuditNotifier(settings).handle(event)
    assert result.notified is False
    assert result.skipped_reason == "missing_repoaudit_credentials"
    assert result.audit_path
    lines = Path(result.audit_path).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["repository"] == "TraceForge/demo"
    assert record["event_type"] == "push"
