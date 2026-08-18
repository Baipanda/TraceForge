from __future__ import annotations

from pathlib import Path
from typing import Any

from traceforge.agent.models import AgentRequest, ContextItem, PromptBundle
from traceforge.agent.skill_loader import SkillLoader


class PromptHarness:
    """Builds model-ready context from workspace files, skills, events, and tools."""

    def __init__(self, workspace_root: Path | str | None = None) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else self._default_workspace_root()
        self.skill_loader = SkillLoader(self.workspace_root)

    def build(
        self,
        request: AgentRequest,
        *,
        context_items: list[ContextItem] | None = None,
        tool_schemas: list[dict[str, Any]] | None = None,
    ) -> PromptBundle:
        selected_skills = self.skill_loader.select_for_text(request.text)
        workspace_sections = [
            self._read_workspace_file("AGENTS.md"),
            self._read_workspace_file("IDENTITY.md"),
            self._read_workspace_file("TOOLS.md"),
            self._read_workspace_file("MEMORY.md"),
        ]
        skill_sections = [
            f"# Skill: {skill.name}\n\n{skill.instructions}" for skill in selected_skills
        ]
        system_prompt = "\n\n".join(section for section in [*workspace_sections, *skill_sections] if section)
        event_context = (
            f"来源: {request.event.source.value}\n"
            f"类型: {request.event.kind.value}\n"
            f"会话: {request.session_key}\n"
            f"频道: {request.event.location.channel_name or request.event.location.channel_id or 'unknown'}\n"
            f"Topic: {request.event.location.topic or 'none'}"
        )
        items = [
            ContextItem(source="workspace_event", content=event_context),
            *(context_items or []),
        ]
        return PromptBundle(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": request.text}],
            tools=tool_schemas or [],
            skills=[skill.name for skill in selected_skills],
            context_items=items,
        )

    def _read_workspace_file(self, relative_path: str) -> str:
        path = self.workspace_root / relative_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def _default_workspace_root(self) -> Path:
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "workspace"
            if candidate.exists():
                return candidate
        return Path.cwd() / "workspace"
