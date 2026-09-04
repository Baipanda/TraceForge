"""Project Admin read tools for progress-sop Scope."""

from __future__ import annotations

from typing import Any

from traceforge.config import TraceForgeSettings, get_settings
from traceforge.infrastructure.project_admin.client import ProjectAdminClient, ProjectAdminError
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry


def register_project_tools(
    registry: ToolRegistry,
    *,
    settings: TraceForgeSettings | None = None,
    client: ProjectAdminClient | None = None,
) -> None:
    settings = settings or get_settings()
    client = client or ProjectAdminClient(settings)

    def _resolve(arguments: dict[str, Any]) -> ToolResult:
        try:
            project = client.resolve(
                project_id=str(arguments.get("project_id") or ""),
                stream=str(arguments.get("stream") or arguments.get("channel_name") or ""),
                topic=str(arguments.get("topic") or ""),
            )
        except ProjectAdminError as exc:
            return ToolResult(
                tool_name="project.resolve",
                ok=False,
                error=str(exc),
                evidence=[{"type": "project.resolve", "ok": False, "error": str(exc)}],
            )
        return ToolResult(
            tool_name="project.resolve",
            ok=True,
            data=project,
            evidence=[
                {
                    "type": "project.resolve",
                    "ok": True,
                    "project_id": project.get("project_id"),
                    "source": "project-admin",
                }
            ],
        )

    def _get(arguments: dict[str, Any]) -> ToolResult:
        try:
            project = client.get(str(arguments.get("project_id") or ""))
        except ProjectAdminError as exc:
            return ToolResult(
                tool_name="project.get",
                ok=False,
                error=str(exc),
                evidence=[{"type": "project.get", "ok": False, "error": str(exc)}],
            )
        return ToolResult(
            tool_name="project.get",
            ok=True,
            data=project,
            evidence=[
                {
                    "type": "project.get",
                    "ok": True,
                    "project_id": project.get("project_id"),
                    "source": "project-admin",
                }
            ],
        )

    registry.register(
        RegisteredTool(
            name="project.resolve",
            description=(
                "Resolve a project from Project Admin DB by project_id or Zulip stream+topic. "
                "Use this for progress-sop Scope; do not invent bindings."
            ),
            schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "stream": {"type": "string"},
                    "channel_name": {"type": "string"},
                    "topic": {"type": "string"},
                },
            },
            handler=_resolve,
        )
    )
    registry.register(
        RegisteredTool(
            name="project.get",
            description="Get one project card from Project Admin by project_id.",
            schema={
                "type": "object",
                "properties": {"project_id": {"type": "string"}},
                "required": ["project_id"],
            },
            handler=_get,
        )
    )
