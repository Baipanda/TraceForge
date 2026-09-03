"""Agent-callable local and MCP tool adapters."""

from traceforge.tools.models import ToolCall, ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry
from traceforge.tools.people_tools import register_people_tools
from traceforge.tools.todo_tools import build_default_tool_registry, register_todo_tools
from traceforge.tools.memory_tools import register_memory_tools
from traceforge.tools.fs_tools import register_fs_tools

__all__ = [
    "RegisteredTool",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
    "build_default_tool_registry",
    "register_people_tools",
    "register_todo_tools",
    "register_memory_tools",
    "register_fs_tools",
]
