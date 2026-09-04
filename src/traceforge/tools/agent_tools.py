"""In-process agent messaging (main → gitea-audit). Not the industry A2A protocol."""

from __future__ import annotations

from typing import Any, Callable

from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry

AgentSendHandler = Callable[[str, dict[str, Any]], ToolResult]


def register_agent_tools(
    registry: ToolRegistry,
    *,
    send_handler: AgentSendHandler | None = None,
) -> None:
    def _send(arguments: dict[str, Any]) -> ToolResult:
        to_agent = str(arguments.get("to") or arguments.get("agent_id") or "").strip()
        if not to_agent:
            return ToolResult(tool_name="agent.send", ok=False, error="to (agent_id) is required")
        if send_handler is None:
            return ToolResult(
                tool_name="agent.send",
                ok=False,
                error="agent.send handler is not configured",
            )
        payload = {
            "text": str(arguments.get("text") or arguments.get("message") or "").strip(),
            "packet": arguments.get("packet") if isinstance(arguments.get("packet"), dict) else {},
            "project_id": str(arguments.get("project_id") or "").strip(),
            "run_id": str(arguments.get("run_id") or "").strip(),
        }
        return send_handler(to_agent, payload)

    registry.register(
        RegisteredTool(
            name="agent.send",
            description=(
                "Send a task packet to another TraceForge agent (in-process). "
                "For progress-sop Audit step, send to gitea-audit with docs/discussion/tasks summaries. "
                "gitea-audit reviews only — it never writes application code."
            ),
            schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Target agentId, e.g. gitea-audit"},
                    "agent_id": {"type": "string"},
                    "text": {"type": "string"},
                    "message": {"type": "string"},
                    "project_id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "packet": {"type": "object"},
                },
                "required": ["to"],
            },
            handler=_send,
        )
    )
