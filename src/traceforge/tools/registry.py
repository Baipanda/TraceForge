from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from traceforge.sandbox.policy import SandboxPolicy
from traceforge.tools.models import ToolCall, ToolResult


ToolHandler = Callable[[dict[str, Any]], ToolResult]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    handler: ToolHandler
    schema: dict[str, Any] = field(default_factory=dict)
    source: str = "local"


class ToolRegistry:
    """Unified registry for local tools and future MCP-backed tools."""

    def __init__(self, policy: SandboxPolicy | None = None) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self.policy = policy

    def register(self, tool: RegisteredTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Tool not registered: {name}") from exc

    def list_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "schema": tool.schema,
                "source": tool.source,
            }
            for tool in self._tools.values()
            if self.policy is None or self.policy.allows_tool(tool.name)
        ]

    def call(self, call: ToolCall) -> ToolResult:
        if self.policy is not None and not self.policy.allows_tool(call.name):
            reason = self.policy.deny_reason(call.name) or f"tool denied: {call.name}"
            return ToolResult(
                tool_name=call.name,
                ok=False,
                error=reason,
                evidence=[{"type": "policy_denied", "tool_name": call.name, "reason": reason}],
                call_id=call.call_id,
            )
        tool = self.get(call.name)
        result = tool.handler(call.arguments)
        return ToolResult(
            tool_name=result.tool_name,
            ok=result.ok,
            data=result.data,
            error=result.error,
            evidence=result.evidence,
            call_id=call.call_id,
        )
