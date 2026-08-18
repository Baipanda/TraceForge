from __future__ import annotations

from typing import Any

from traceforge.domain.events import (
    ActorRef,
    EventKind,
    EventSource,
    WorkspaceEvent,
    WorkspaceLocation,
)


def normalize_zulip_payload(payload: dict[str, Any]) -> WorkspaceEvent:
    """Normalize a Zulip-like payload into a WorkspaceEvent.

    The function accepts two shapes:
    1. raw Zulip event payload containing a `message` object;
    2. simplified smoke-test payload with top-level fields.
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

    return WorkspaceEvent(
        source=EventSource.ZULIP,
        kind=EventKind.MESSAGE_CREATED,
        actor=ActorRef(
            external_id=sender_id,
            display_name=str(sender_name) if sender_name else None,
            email=sender_email or None,
        ),
        location=WorkspaceLocation(
            workspace_id=str(payload.get("workspace_id") or "default"),
            channel_id=str(stream_id) if stream_id is not None else None,
            channel_name=str(stream_name) if stream_name else None,
            topic=str(topic) if topic else None,
        ),
        payload={
            "text": _strip_zulip_markup(str(content)),
            "raw": payload,
        },
        external_event_id=str(payload.get("id") or message_id) if (payload.get("id") or message_id) else None,
    )


def _display_recipient_name(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _strip_zulip_markup(text: str) -> str:
    return text.replace("<p>", "").replace("</p>", "").strip()
