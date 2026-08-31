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
        mentions_todo = any(token in lowered for token in ("todo", "待办", "todos"))
        create_requested = any(
            token in lowered for token in ("创建", "新增", "发布", "安排", "记录", "加一个", "帮我加")
        )
        list_requested = any(
            token in lowered
            for token in ("查询", "查看", "列出", "展示", "有哪些", "list", "看看", "查一下")
        )
        update_requested = any(
            token in lowered
            for token in (
                "更新",
                "修改",
                "改派",
                "完成",
                "关闭",
                "标记",
                "做完",
                "搞定",
                "弄完",
                "写完",
                "改成",
                "改为",
                "设为",
                "标成",
                "标为",
                "update",
                "complete",
                "done",
                "finished",
                "close",
            )
        )
        delete_requested = any(
            token in lowered for token in ("删除", "删掉", "去掉", "移除", "delete", "remove")
        )
        summary_requested = any(
            token in lowered for token in ("总结", "summary", "归纳", "汇总")
        )
        subtree_requested = any(
            token in lowered
            for token in (
                "subtree",
                "组织树",
                "组织架构",
                "子树",
                "子subtree",
                "挂了哪些",
                "下面有哪些",
                "有哪些子",
            )
        )

        if create_requested and not update_requested and not delete_requested:
            selected.append("todo-create")
        if delete_requested:
            selected.append("todo-delete")
        elif update_requested:
            selected.append("todo-update")
        if subtree_requested:
            selected.append("subtree-list")
        elif list_requested and not update_requested:
            selected.append("todo-list")
        if summary_requested:
            selected.append("topic-summary")

        # Soft fallback: user talked about a Todo but no verb matched. Give the model
        # list+update playbooks so natural phrases can still act (LLM decides).
        if mentions_todo and not selected:
            selected.extend(["todo-list", "todo-update"])

        result: list[SkillDefinition] = []
        for name in dict.fromkeys(selected):
            try:
                result.append(self.load(name))
            except FileNotFoundError:
                continue
        return result
