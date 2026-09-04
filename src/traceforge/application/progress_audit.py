"""gitea-audit progress review (read-only). Never writes application code."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from traceforge.agents import load_agents_config, resolve_sessions_root, resolve_workspace_root
from traceforge.config import TraceForgeSettings, get_settings
from traceforge.session.transcript import JsonlSessionStore, SessionEvent


@dataclass(frozen=True)
class ProgressAuditResult:
    agent_id: str
    session_key: str
    markdown: str
    evidence: list[dict[str, Any]]


class ProgressAuditService:
    """Handles main → gitea-audit progress-sop Audit requests."""

    AGENT_ID = "gitea-audit"

    def __init__(self, settings: TraceForgeSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.agents_config = load_agents_config(self.settings.agents_config_path or None)
        entry = self.agents_config.get(self.AGENT_ID)
        data_root = Path(self.settings.traceforge_db_path).expanduser().resolve().parent
        self.workspace_root = resolve_workspace_root(entry)
        self.session_store = JsonlSessionStore(
            resolve_sessions_root(entry, data_root=data_root)
        )
        self.repo_root = Path(__file__).resolve().parents[3]

    def handle(self, packet: dict[str, Any]) -> ProgressAuditResult:
        project_id = str(packet.get("project_id") or "unknown")
        run_id = str(packet.get("run_id") or "adhoc")
        docs_md = str(packet.get("docs_md") or "")
        discussion_md = str(packet.get("discussion_md") or "")
        tasks_md = str(packet.get("tasks_md") or "")
        docs_excerpt = self._read_shared_docs(packet)
        markdown = self._build_audit_markdown(
            project_id=project_id,
            docs_md=docs_md,
            docs_excerpt=docs_excerpt,
            discussion_md=discussion_md,
            tasks_md=tasks_md,
            project=packet.get("project") if isinstance(packet.get("project"), dict) else {},
        )
        session_key = f"agent:gitea-audit:progress-sop:{project_id}:{run_id}"
        self.session_store.append(
            session_key,
            SessionEvent(
                type="user",
                content=f"progress-sop audit request project={project_id} run={run_id}",
            ),
        )
        self.session_store.append(
            session_key,
            SessionEvent(type="assistant", content=markdown),
        )
        return ProgressAuditResult(
            agent_id=self.AGENT_ID,
            session_key=session_key,
            markdown=markdown,
            evidence=[
                {
                    "type": "agent.send",
                    "to": self.AGENT_ID,
                    "ok": True,
                    "project_id": project_id,
                    "run_id": run_id,
                    "mode": "progress-audit",
                }
            ],
        )

    def _read_shared_docs(self, packet: dict[str, Any]) -> str:
        project = packet.get("project") if isinstance(packet.get("project"), dict) else {}
        docs_root = str(project.get("docs_root") or packet.get("docs_root") or "").strip()
        if not docs_root:
            return ""
        root = Path(docs_root)
        if not root.is_absolute():
            root = (self.repo_root / docs_root).resolve()
        chunks: list[str] = []
        for name in (
            str(project.get("prd_path") or "PRD.md"),
            str(project.get("tech_path") or "TECH.md"),
            "STATUS.md",
        ):
            path = root / name if not Path(name).is_absolute() else Path(name)
            if not path.exists() and name:
                path = root / Path(name).name
            if path.exists() and path.is_file():
                text = path.read_text(encoding="utf-8")[:4000]
                chunks.append(f"### {path.name}\n{text}")
        return "\n\n".join(chunks)

    def _build_audit_markdown(
        self,
        *,
        project_id: str,
        docs_md: str,
        docs_excerpt: str,
        discussion_md: str,
        tasks_md: str,
        project: dict[str, Any],
    ) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        gaps: list[str] = []
        if not (docs_md or docs_excerpt).strip():
            gaps.append("缺少可读的 PRD/TECH 文档摘录")
        if not discussion_md.strip():
            gaps.append("讨论摘要为空（Topic 可能无消息或未配置）")
        if not tasks_md.strip():
            gaps.append("任务摘要为空（Todo 域可能未绑定）")

        repo = ""
        owner = str(project.get("gitea_owner") or "").strip()
        name = str(project.get("gitea_repo") or "").strip()
        if owner and name:
            repo = f"{owner}/{name}@{project.get('default_branch') or 'main'}"
        else:
            gaps.append("未绑定 Gitea 仓库（本次仅对照文档/讨论/任务）")

        alignment = (
            "有文档与任务信号，可做对齐检查"
            if (docs_md or docs_excerpt) and tasks_md
            else "证据不足，对齐结论仅供参考"
        )
        gap_block = "\n".join(f"- {item}" for item in gaps) if gaps else "- 未发现明显结构性缺口"
        return (
            f"## RepoAudit 进度审查：`{project_id}`\n"
            f"- 时间：{now}\n"
            f"- 仓库：{repo or '（未绑定）'}\n"
            f"- 模式：**只审不写**（不生成业务代码、不开 PR）\n\n"
            f"### 对齐判断\n"
            f"- {alignment}\n\n"
            f"### 文档侧\n"
            f"{(docs_md or docs_excerpt or '_无_')[:2500]}\n\n"
            f"### 讨论侧（main 摘要）\n"
            f"{(discussion_md or '_无_')[:2000]}\n\n"
            f"### 任务侧（main 摘要）\n"
            f"{(tasks_md or '_无_')[:2000]}\n\n"
            f"### 风险与缺口\n"
            f"{gap_block}\n\n"
            f"### 建议（由人写代码）\n"
            f"1. 对照 PRD 验收点核对未完成 Todo\n"
            f"2. 把讨论里的未决问题收敛成可执行任务\n"
            f"3. 代码变更仍由开发者提交；RepoAudit 仅跟审查结论\n"
        )
