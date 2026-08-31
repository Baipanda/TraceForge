from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from traceforge.core.events import ActorRef


class ZulipConversationType(StrEnum):
    STREAM = "stream"
    PRIVATE = "private"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ZulipConversationContext:
    """Structured context extracted from one Zulip message.

    This is the boundary between a channel adapter and the agent engine.
    It contains conversation identity and metadata, not business decisions.
    """

    workspace_id: str
    message_id: str | None
    message_type: ZulipConversationType
    sender: ActorRef
    participants: tuple[ActorRef, ...] = ()
    stream_id: str | None = None
    stream_name: str | None = None
    topic: str | None = None
    text: str = ""
    mentions: tuple[str, ...] = ()

    @property
    def conversation_label(self) -> str:
        if self.message_type == ZulipConversationType.PRIVATE:
            return "private"
        if self.stream_name:
            return self.stream_name
        if self.stream_id:
            return self.stream_id
        return "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender": _actor_to_dict(self.sender),
            "participants": [_actor_to_dict(item) for item in self.participants],
            "stream_id": self.stream_id,
            "stream_name": self.stream_name,
            "topic": self.topic,
            "text": self.text,
            "mentions": list(self.mentions),
            "conversation_label": self.conversation_label,
        }


def _actor_to_dict(actor: ActorRef) -> dict[str, str | None]:
    return {
        "external_id": actor.external_id,
        "display_name": actor.display_name,
        "email": actor.email,
        "person_id": actor.person_id,
    }
