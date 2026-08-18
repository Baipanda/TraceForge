from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from traceforge.domain.events import WorkspaceEvent


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepKind(StrEnum):
    MODEL = "model"
    TOOL = "tool"
    FINAL = "final"
    ERROR = "error"


@dataclass(frozen=True)
class AgentRequest:
    """Gateway 交给 AgentRuntime 的标准请求。"""

    event: WorkspaceEvent
    session_key: str
    request_id: str = field(default_factory=lambda: str(uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return str(self.event.payload.get("text") or "")


@dataclass(frozen=True)
class ContextItem:
    """进入 Harness 的一条有来源上下文。"""

    source: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptBundle:
    """Harness 组装后的模型输入。"""

    system_prompt: str
    messages: list[dict[str, str]]
    tools: list[dict[str, Any]] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    context_items: list[ContextItem] = field(default_factory=list)


@dataclass(frozen=True)
class RunStep:
    kind: StepKind
    status: RunStatus
    input: Any = None
    output: Any = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


@dataclass
class AgentRun:
    """一次 Agent 执行的可审计轨迹。"""

    request: AgentRequest
    status: RunStatus = RunStatus.CREATED
    steps: list[RunStep] = field(default_factory=list)
    final_text: str | None = None
    run_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


@dataclass(frozen=True)
class GatewayResponse:
    request_id: str
    run_id: str | None
    reply_text: str
    status: RunStatus
    evidence: list[dict[str, Any]] = field(default_factory=list)
