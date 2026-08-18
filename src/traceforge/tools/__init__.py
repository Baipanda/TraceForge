"""Agent-callable local and MCP tool adapters."""

from traceforge.tools.models import ToolCall, ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry

__all__ = ["RegisteredTool", "ToolCall", "ToolRegistry", "ToolResult"]
