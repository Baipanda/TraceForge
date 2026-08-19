from __future__ import annotations

from typing import Any

from traceforge.infrastructure.identity.people_directory import IdentityRecord, PeopleDirectory
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry


def register_people_tools(registry: ToolRegistry, people_directory: PeopleDirectory) -> None:
    registry.register(
        RegisteredTool(
            name="people.resolve",
            description="Resolve a person by name, email, Zulip username, or alias",
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=lambda arguments: _resolve_person(people_directory, arguments),
        )
    )


def _resolve_person(people_directory: PeopleDirectory, arguments: dict[str, Any]) -> ToolResult:
    query = str(arguments.get("query") or "")
    record = people_directory.resolve(query)
    if record is None:
        return ToolResult(
            tool_name="people.resolve",
            ok=False,
            error=f"没有找到身份：{query}",
            data={"query": query, "person": None},
        )
    return ToolResult(
        tool_name="people.resolve",
        ok=True,
        data={"query": query, "person": record.to_dict()},
    )

