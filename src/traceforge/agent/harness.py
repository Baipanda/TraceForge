from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from traceforge.agent.models import AgentRequest, ContextItem, PromptBundle
from traceforge.agent.skill_loader import SkillLoader
from traceforge.memory.markdown_store import MarkdownMemoryStore


class PromptHarness:
    """Builds model-ready context from workspace files, skills, events, and tools."""

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        *,
        memory_store: MarkdownMemoryStore | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else self._default_workspace_root()
        self.skill_loader = SkillLoader(self.workspace_root)
        self.memory_store = memory_store or MarkdownMemoryStore(self.workspace_root)

    def build(
        self,
        request: AgentRequest,
        *,
        context_items: list[ContextItem] | None = None,
        tool_schemas: list[dict[str, Any]] | None = None,
    ) -> PromptBundle:
        selected_skills = self.skill_loader.select_for_text(request.text)
        preference = self.memory_store.read_preference(request.event.actor.person_id)
        workspace_sections = [
            self._read_workspace_file("AGENTS.md"),
            self._read_workspace_file("IDENTITY.md"),
            self._read_workspace_file("TOOLS.md"),
            self._read_workspace_file("MEMORY.md"),
        ]
        if preference:
            workspace_sections.append("# Preference (current speaker only)\n\n" + preference)
        skill_sections = [
            f"# Skill: {skill.name}\n\n{skill.instructions}" for skill in selected_skills
        ]
        system_prompt = "\n\n".join(section for section in [*workspace_sections, *skill_sections] if section)
        system_prompt = (
            "你是 TraceForge 的 Agent。请基于当前 Context 和 Workspace 规则完成用户请求。\n"
            "需要真实数据或执行动作时，必须调用工具；只有工具返回成功后才能声称动作完成。\n"
            "如果用户只是闲聊、问候、要求介绍你的能力或解释概念，不要调用业务工具。\n"
            "用户说「以后/之后/记住/下次请…」这类长期习惯时，调用 memory.remember，"
            "person_id 使用当前发言人的 person_id。\n"
            "需要回忆历史决策、日记式情景时，调用 memory.search / memory.get；"
            "不要编造未检索到的记忆。\n"
            "如果信息不足，先向用户澄清，不要编造数据库、人员或 Topic 信息。\n\n"
            + system_prompt
        )
        event_context = (
            f"来源: {request.event.source.value}\n"
            f"类型: {request.event.kind.value}\n"
            f"会话: {request.session_key}\n"
            f"发言人 person_id: {request.event.actor.person_id or 'unknown'}\n"
            f"频道: {request.event.location.channel_name or request.event.location.channel_id or 'unknown'}\n"
            f"Topic: {request.event.location.topic or 'none'}"
        )
        structured_context = request.metadata.get("zulip_context")
        if isinstance(structured_context, dict):
            event_context += (
                "\n结构化 Zulip Context:\n"
                + json.dumps(structured_context, ensure_ascii=False, indent=2)
            )
        items = [
            ContextItem(source="workspace_event", content=event_context),
            *(context_items or []),
        ]
        if preference:
            items.append(
                ContextItem(
                    source="memory/preference",
                    content=preference,
                    metadata={"person_id": request.event.actor.person_id},
                )
            )
        context_message = "\n\n".join(f"[{item.source}]\n{item.content}" for item in items)
        history = [dict(message) for message in request.session_messages]
        current_user = {
            "role": "user",
            "content": f"{context_message}\n\n[用户消息]\n{request.text}",
        }
        return PromptBundle(
            system_prompt=system_prompt,
            messages=[*history, current_user],
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
