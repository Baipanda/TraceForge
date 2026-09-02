"""Markdown-backed workspace memory (canonical text on disk)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

MemoryKind = Literal["core", "preference", "daily", "decision"]


@dataclass(frozen=True)
class MemoryFileRef:
    kind: MemoryKind
    relative_path: str
    absolute_path: Path
    person_id: str | None = None


class MarkdownMemoryStore:
    """Authoritative memory files under workspace/."""

    def __init__(self, workspace_root: Path | str | None = None) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else self._default_workspace_root()
        self.memory_root = self.workspace_root / "memory"
        self.preferences_root = self.memory_root / "preferences"
        self.ensure_layout()

    def ensure_layout(self) -> None:
        self.preferences_root.mkdir(parents=True, exist_ok=True)
        decision = self.memory_root / "DECISION.md"
        if not decision.exists():
            decision.write_text(
                "# Decisions\n\n重要决策与 Todo 变更摘要。靠 memory.search 召回，不自动注入 prompt。\n",
                encoding="utf-8",
            )
        readme = self.preferences_root / "README.md"
        if not readme.exists():
            readme.write_text(
                "# Preferences\n\n按 person_id 分文件，例如 `<person_id>.md`。仅注入当前发言人对应文件。\n",
                encoding="utf-8",
            )

    def core_path(self) -> Path:
        return self.workspace_root / "MEMORY.md"

    def preference_path(self, person_id: str) -> Path:
        safe = _safe_person_id(person_id)
        return self.preferences_root / f"{safe}.md"

    def decision_path(self) -> Path:
        return self.memory_root / "DECISION.md"

    def daily_path(self, day: str | None = None) -> Path:
        day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.memory_root / f"{day}.md"

    def read_core(self) -> str:
        return _read_text(self.core_path())

    def read_preference(self, person_id: str | None) -> str:
        if not person_id:
            return ""
        return _read_text(self.preference_path(person_id))

    def read_file(self, relative_path: str) -> str:
        path = self._resolve_relative(relative_path)
        if path is None:
            return ""
        return _read_text(path)

    def append_preference(self, person_id: str, note: str, *, source: str = "agent") -> Path:
        path = self.preference_path(person_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        block = f"\n## {stamp}\n\n- source: {source}\n- {note.strip()}\n"
        if not path.exists():
            header = (
                f"# Preferences for `{person_id}`\n\n"
                "用户习惯与个人偏好。仅对该 person_id 自动注入。\n"
            )
            path.write_text(header + block, encoding="utf-8")
        else:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(block)
        return path

    def append_decision(self, note: str, *, source: str = "agent", topic: str | None = None) -> Path:
        path = self.decision_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        meta = f"topic={topic}" if topic else "topic=-"
        block = f"\n## {stamp}\n\n- source: {source}\n- {meta}\n- {note.strip()}\n"
        if not path.exists():
            path.write_text("# Decisions\n" + block, encoding="utf-8")
        else:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(block)
        return path

    def append_daily(self, note: str, *, source: str = "flush", day: str | None = None) -> Path:
        path = self.daily_path(day)
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%H:%M UTC")
        block = f"\n## {stamp} ({source})\n\n{note.strip()}\n"
        if not path.exists():
            day_label = path.stem
            path.write_text(f"# Daily notes {day_label}\n" + block, encoding="utf-8")
        else:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(block)
        return path

    def iter_indexable_files(self) -> list[MemoryFileRef]:
        refs: list[MemoryFileRef] = []
        core = self.core_path()
        if core.exists():
            refs.append(MemoryFileRef(kind="core", relative_path="MEMORY.md", absolute_path=core))
        decision = self.decision_path()
        if decision.exists():
            refs.append(
                MemoryFileRef(
                    kind="decision",
                    relative_path="memory/DECISION.md",
                    absolute_path=decision,
                )
            )
        if self.preferences_root.exists():
            for path in sorted(self.preferences_root.glob("*.md")):
                if path.name.upper() == "README.MD":
                    continue
                person_id = path.stem
                refs.append(
                    MemoryFileRef(
                        kind="preference",
                        relative_path=f"memory/preferences/{path.name}",
                        absolute_path=path,
                        person_id=person_id,
                    )
                )
        if self.memory_root.exists():
            for path in sorted(self.memory_root.glob("*.md")):
                if path.name.upper() == "DECISION.MD":
                    continue
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
                    refs.append(
                        MemoryFileRef(
                            kind="daily",
                            relative_path=f"memory/{path.name}",
                            absolute_path=path,
                        )
                    )
        return refs

    def _resolve_relative(self, relative_path: str) -> Path | None:
        rel = relative_path.replace("\\", "/").lstrip("./")
        if ".." in rel.split("/"):
            return None
        candidate = (self.workspace_root / rel).resolve()
        root = self.workspace_root.resolve()
        if not str(candidate).startswith(str(root)):
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate

    def _default_workspace_root(self) -> Path:
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "workspace"
            if candidate.exists():
                return candidate
        return Path.cwd() / "workspace"


def _safe_person_id(person_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", person_id.strip())
    return cleaned[:80] or "unknown"


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()
