"""Session transcript store (OpenClaw-inspired, JSONL per session_key)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

SessionEventType = Literal["user", "assistant", "tool"]

# Emulate OpenClaw agents.defaults.compaction.keepRecentTokens default.
DEFAULT_KEEP_RECENT_TOKENS = 20_000


@dataclass(frozen=True)
class SessionEvent:
    type: SessionEventType
    content: str
    id: str = field(default_factory=lambda: str(uuid4()))
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    person_id: str | None = None
    name: str | None = None  # tool name
    call_id: str | None = None
    ok: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionEvent | None:
        event_type = data.get("type")
        if event_type not in {"user", "assistant", "tool"}:
            return None
        content = data.get("content")
        if not isinstance(content, str):
            return None
        return cls(
            type=event_type,  # type: ignore[arg-type]
            content=content,
            id=str(data.get("id") or uuid4()),
            ts=str(data.get("ts") or datetime.now(timezone.utc).isoformat()),
            person_id=_optional_str(data.get("person_id")),
            name=_optional_str(data.get("name")),
            call_id=_optional_str(data.get("call_id")),
            ok=data.get("ok") if isinstance(data.get("ok"), bool) else None,
        )


class JsonlSessionStore:
    """One JSONL file per session_key under ``<root>/sessions/``."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_key: str) -> Path:
        digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:32]
        safe = _safe_filename_fragment(session_key)
        return self.root / f"{safe}-{digest}.jsonl"

    def load_events(self, session_key: str) -> list[SessionEvent]:
        path = self.path_for(session_key)
        if not path.exists():
            return []
        events: list[SessionEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            event = SessionEvent.from_dict(payload)
            if event is not None:
                events.append(event)
        return events

    def append(self, session_key: str, events: list[SessionEvent] | SessionEvent) -> None:
        items = events if isinstance(events, list) else [events]
        if not items:
            return
        path = self.path_for(session_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for event in items:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def build_session_messages(
    events: list[SessionEvent],
    *,
    keep_recent_tokens: int = DEFAULT_KEEP_RECENT_TOKENS,
) -> list[dict[str, Any]]:
    """Project transcript events into chat messages (OpenClaw-style recent tail).

    Walks backward accumulating token estimates until ``keep_recent_tokens``,
    then returns messages in chronological order. Does not include a synthetic
    current-turn user message — Harness adds that from the live event.
    """
    if keep_recent_tokens <= 0 or not events:
        return []
    kept: list[SessionEvent] = []
    used = 0
    for event in reversed(events):
        cost = estimate_tokens(_event_text_for_budget(event))
        if kept and used + cost > keep_recent_tokens:
            break
        kept.append(event)
        used += cost
    kept.reverse()
    return [project_session_event(event) for event in kept]


def project_session_event(event: SessionEvent) -> dict[str, Any]:
    if event.type == "user":
        return {"role": "user", "content": event.content}
    if event.type == "assistant":
        return {"role": "assistant", "content": event.content}
    # tool
    payload = {
        "role": "tool",
        "content": event.content,
    }
    if event.name:
        payload["name"] = event.name
    if event.call_id:
        payload["tool_call_id"] = event.call_id
    return payload


def estimate_tokens(text: str) -> int:
    """Rough token estimate: CJK ~1 tok/char, other ~4 chars/tok (OpenClaw-ish)."""
    if not text:
        return 1
    cjk = 0
    other = 0
    for char in text:
        code = ord(char)
        if code > 0x2E80 or 0x3400 <= code <= 0x9FFF:
            cjk += 1
        else:
            other += 1
    return max(1, cjk + (other + 3) // 4)


def _event_text_for_budget(event: SessionEvent) -> str:
    parts = [event.content]
    if event.name:
        parts.append(event.name)
    return " ".join(parts)


def _safe_filename_fragment(session_key: str) -> str:
    fragment = re.sub(r"[^a-zA-Z0-9._-]+", "_", session_key)
    return (fragment[:48] or "session").strip("._-") or "session"


def _optional_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
