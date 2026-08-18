from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from traceforge.config import get_settings
from traceforge.domain.events import WorkspaceEvent
from traceforge.infrastructure.llm.deepseek import DeepSeekClient


@dataclass(frozen=True)
class ProcessedEvent:
    event_id: str
    route_key: str
    intent: str
    reply_text: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProcessWorkspaceEvent:
    """First application use case.

    This is intentionally small. It proves the clean path:
    external adapter -> WorkspaceEvent -> application use case -> reply.
    Real agents, tools, RAG, and persistence will be attached behind this use case.
    """

    def execute(self, event: WorkspaceEvent) -> ProcessedEvent:
        text = str(event.payload.get("text") or "").strip()
        intent = self._detect_intent(text)
        evidence = [
            {
                "type": "workspace_event",
                "event_id": event.event_id,
                "source": event.source.value,
                "external_event_id": event.external_event_id,
            }
        ]
        reply = self._build_reply(event, intent)
        llm_reply, llm_status = self._try_llm_reply(event, intent)
        if llm_reply is not None:
            reply = llm_reply
            evidence.append({"type": "llm", "provider": "deepseek", "status": llm_status})
        return ProcessedEvent(
            event_id=event.event_id,
            route_key=event.route_key(),
            intent=intent,
            reply_text=reply,
            evidence=evidence,
        )

    def _detect_intent(self, text: str) -> str:
        lowered = text.lower()
        if any(token in lowered for token in ("todo", "待办", "任务", "发布")):
            return "todo.command"
        if any(token in lowered for token in ("总结", "summary", "归纳")):
            return "topic.summarize"
        if any(token in lowered for token in ("修了吗", "修复", "bug", "漏洞", "安全")):
            return "issue.status"
        return "chat.echo"

    def _build_reply(self, event: WorkspaceEvent, intent: str) -> str:
        actor = event.actor.display_name or event.actor.email or event.actor.external_id
        topic = event.location.topic or "无 Topic"
        channel = event.location.channel_name or event.location.channel_id or "未知频道"
        return (
            f"TraceForge 已收到来自 {actor} 的请求。\n\n"
            f"- 来源：{event.source.value}\n"
            f"- 频道：{channel}\n"
            f"- Topic：{topic}\n"
            f"- 识别意图：{intent}\n\n"
            "当前是最小部署版本：事件接入已经打通，下一步会接入 Todo、RAG 和 Agent Runtime。"
        )

    def _try_llm_reply(self, event: WorkspaceEvent, intent: str) -> tuple[str | None, str]:
        settings = get_settings()
        if not settings.llm_enabled:
            return None, "disabled"
        try:
            return DeepSeekClient(settings).generate_workspace_reply(event, intent).content, "used"
        except Exception as exc:
            return (
                self._build_reply(event, intent)
                + f"\n\n[模型回复暂不可用，已使用规则回复。原因：{type(exc).__name__}]"
            ), "fallback"
