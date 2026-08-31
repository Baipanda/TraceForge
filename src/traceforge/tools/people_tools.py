from __future__ import annotations

from typing import Any

from traceforge.infrastructure.identity.person_store import PersonRecord, PersonStore
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry


def register_people_tools(registry: ToolRegistry, person_store: PersonStore) -> None:
    registry.register(
        RegisteredTool(
            name="people.resolve",
            description="Resolve a workspace person by person_id, display name, email, or Zulip external_id",
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
            handler=lambda arguments: _resolve_person(person_store, arguments),
        )
    )


def _resolve_person(person_store: PersonStore, arguments: dict[str, Any]) -> ToolResult:
    query = str(arguments.get("query") or "")
    record = person_store.resolve(query)
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
