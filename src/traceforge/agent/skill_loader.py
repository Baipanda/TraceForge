from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    path: Path
    instructions: str


class SkillLoader:
    """Loads markdown skills from the TraceForge agent workspace."""

    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root)
        self.skills_root = self.workspace_root / "skills"

    def list_skill_names(self) -> list[str]:
        if not self.skills_root.exists():
            return []
        return sorted(
            item.name
            for item in self.skills_root.iterdir()
            if item.is_dir() and (item / "SKILL.md").exists()
        )

    def load(self, name: str) -> SkillDefinition:
        skill_path = self.skills_root / name / "SKILL.md"
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill not found: {name}")
        return SkillDefinition(
            name=name,
            path=skill_path,
            instructions=skill_path.read_text(encoding="utf-8"),
        )

    def select_for_text(self, text: str) -> list[SkillDefinition]:
        lowered = text.lower()
        selected: list[str] = []
        create_requested = any(
            token in lowered for token in ("创建", "新增", "发布", "安排", "记录")
        )
        list_requested = any(
            token in lowered for token in ("查询", "查看", "列出", "展示", "有哪些", "list")
        )
        summary_requested = any(
            token in lowered for token in ("总结", "summary", "归纳", "汇总")
        )

        if create_requested:
            selected.append("todo-create")
        elif list_requested:
            selected.append("todo-list")
        if summary_requested:
            selected.append("topic-summary")

        result: list[SkillDefinition] = []
        for name in dict.fromkeys(selected):
            try:
                result.append(self.load(name))
            except FileNotFoundError:
                continue
        return result
