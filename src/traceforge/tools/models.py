from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    ok: bool
    data: Any = None
    error: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    call_id: str | None = None
