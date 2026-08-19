from __future__ import annotations

import re
from typing import Any

from traceforge.context.models import ZulipConversationContext, ZulipConversationType
from traceforge.core.events import ActorRef, WorkspaceEvent


class ZulipContextBuilder:
    """Turns a normalized WorkspaceEvent into agent-ready Zulip context."""

    def build(self, event: WorkspaceEvent) -> ZulipConversationContext:
        raw = event.payload.get("raw")
        payload = raw if isinstance(raw, dict) else {}
        message = payload.get("message")
        message = message if isinstance(message, dict) else payload

        message_type = _conversation_type(message.get("type"))
        sender = event.actor
        participants = _participants(message, sender)
        display_recipient = message.get("display_recipient")
        stream_name = (
            display_recipient
            if message_type == ZulipConversationType.STREAM and isinstance(display_recipient, str)
            else event.location.channel_name
        )
        stream_id = _optional_string(message.get("stream_id")) or event.location.channel_id
        topic = (
            _optional_string(message.get("subject"))
            or _optional_string(message.get("topic"))
            or event.location.topic
        )
        text = str(event.payload.get("text") or "")

        return ZulipConversationContext(
            workspace_id=event.location.workspace_id,
            message_id=event.external_event_id,
            message_type=message_type,
            sender=sender,
            participants=participants,
            stream_id=stream_id,
            stream_name=stream_name,
            topic=topic,
            text=text,
            mentions=tuple(_extract_mentions(text)),
        )


def _conversation_type(value: Any) -> ZulipConversationType:
    if value == "stream":
        return ZulipConversationType.STREAM
    if value == "private":
        return ZulipConversationType.PRIVATE
    return ZulipConversationType.UNKNOWN


def _participants(message: dict[str, Any], sender: ActorRef) -> tuple[ActorRef, ...]:
    recipients = message.get("display_recipient")
    result: list[ActorRef] = []
    if isinstance(recipients, list):
        for item in recipients:
            if not isinstance(item, dict):
                continue
            email = _optional_string(item.get("email"))
            external_id = _optional_string(item.get("id")) or email or "unknown"
            result.append(
                ActorRef(
                    external_id=external_id,
                    display_name=_optional_string(item.get("full_name")),
                    email=email,
                )
            )
    if not any(_same_actor(item, sender) for item in result):
        result.insert(0, sender)
    return tuple(result)


def _same_actor(left: ActorRef, right: ActorRef) -> bool:
    if left.email and right.email:
        return left.email.casefold() == right.email.casefold()
    return left.external_id == right.external_id


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_mentions(text: str) -> list[str]:
    mentions: list[str] = []
    for match in re.finditer(r"@(?:\*\*([^*]+)\*\*|([A-Za-z0-9_.+\-@]+))", text):
        value = (match.group(1) or match.group(2) or "").strip()
        if value and value.casefold() not in {item.casefold() for item in mentions}:
            mentions.append(value)
    return mentions
