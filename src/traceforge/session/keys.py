from __future__ import annotations

import hashlib
from urllib.parse import quote

from traceforge.context.models import ZulipConversationContext, ZulipConversationType


class SessionKeyResolver:
    """Produces stable session identities without creating one per message."""

    def resolve(self, context: ZulipConversationContext) -> str:
        prefix = f"zulip:{quote(context.workspace_id, safe='')}"
        if context.message_type == ZulipConversationType.PRIVATE:
            return f"{prefix}:dm:{self._private_participant_digest(context)}"

        stream = context.stream_id or context.stream_name or "_"
        topic = (context.topic or "_").strip().casefold()
        return (
            f"{prefix}:stream:{quote(stream, safe='')}"
            f":topic:{quote(topic, safe='')}"
        )

    def _private_participant_digest(self, context: ZulipConversationContext) -> str:
        identities = sorted(
            (
                (item.email or item.external_id).strip().casefold()
                for item in context.participants
                if item.email or item.external_id
            )
        )
        raw = "|".join(identities) or context.sender.external_id
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
