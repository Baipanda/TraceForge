from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any

from traceforge.core.events import (
    ActorRef,
    EventKind,
    EventSource,
    WorkspaceEvent,
    WorkspaceLocation,
)
from traceforge.infrastructure.identity.person_store import PROVIDER_ZULIP, PersonStore


def normalize_zulip_payload(
    payload: dict[str, Any],
    *,
    person_store: PersonStore | None = None,
) -> WorkspaceEvent:
    """Normalize a Zulip-like payload into a WorkspaceEvent.

    The function accepts two shapes:
    1. raw Zulip event payload containing a `message` object;
    2. simplified smoke-test payload with top-level fields.

    Workspace Person mapping runs here: actor.person_id is set from SQLite.
    """

    message = payload.get("message") if isinstance(payload.get("message"), dict) else payload

    sender_email = str(message.get("sender_email") or payload.get("sender_email") or "")
    sender_id = str(message.get("sender_id") or sender_email or "unknown")
    sender_name = message.get("sender_full_name") or payload.get("sender_full_name")

    stream_id = message.get("stream_id") or payload.get("stream_id")
    stream_name = _display_recipient_name(message.get("display_recipient")) or payload.get(
        "stream_name"
    )
    topic = message.get("subject") or payload.get("topic")
    content = message.get("content") or payload.get("content") or payload.get("text") or ""
    message_id = message.get("id") or payload.get("message_id")

    store = person_store or PersonStore()
    person = store.resolve_or_create(
        provider=PROVIDER_ZULIP,
        external_id=sender_id,
        email=sender_email or None,
        display_name=str(sender_name) if sender_name else None,
    )

    return WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(
            external_id=sender_id,
            display_name=str(sender_name) if sender_name else person.display_name,
            email=sender_email or person.primary_email,
            person_id=person.person_id,
        ),
        location=WorkspaceLocation(
            workspace_id=str(payload.get("workspace_id") or "default"),
            channel_id=str(stream_id) if stream_id is not None else None,
            channel_name=str(stream_name) if stream_name else None,
            topic=str(topic) if topic else None,
        ),
        payload={
            "text": strip_zulip_markup(str(content)),
            "raw": payload,
        },
        external_event_id=str(payload.get("id") or message_id) if (payload.get("id") or message_id) else None,
        occurred_at=_parse_zulip_timestamp(message.get("timestamp") or payload.get("timestamp")),
    )


def _display_recipient_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _parse_zulip_timestamp(value: Any) -> datetime:
    """Prefer Zulip message timestamp; fall back to server UTC now."""
    if value is None or value == "":
        return datetime.now(timezone.utc)
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        text = str(value).strip()
        if text.isdigit():
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return datetime.now(timezone.utc)


def strip_zulip_markup(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_strip_zulip_markup = strip_zulip_markup
