"""progress-sop: hardcoded progress checkup pipeline with HITL + A2A audit."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from traceforge.agent.models import AgentRequest, GatewayResponse, RunStatus
from traceforge.application.progress_audit import ProgressAuditService
from traceforge.application.todo_workflow import TodoWorkflow
from traceforge.config import TraceForgeSettings, get_settings
from traceforge.core.events import WorkspaceEvent
from traceforge.core.todos import TodoAction, TodoCommand
from traceforge.infrastructure.project_admin.client import ProjectAdminClient, ProjectAdminError
from traceforge.infrastructure.zulip.client import ZulipApiClient
from traceforge.tools.models import ToolResult
from traceforge.tools.zulip_choice_tools import build_zform_choices

PIPELINE = "progress-sop"

_TRIGGER_RE = re.compile(
    r"(?:项目进度|进度体检|进度\s*SOP|progress\s*sop)\s*[:：\s]+([a-z0-9][a-z0-9\-]*)",
    re.IGNORECASE,
)
_RESUME_RE = re.compile(
    r"sop\s+continue\s+run_id=([a-zA-Z0-9\-]+)\s+window=(\d+)\s+include_audit=([01])\s+focus=(\w+)",
    re.IGNORECASE,
)
_FOLLOWUP_RE = re.compile(
    r"sop\s+followup\s+run_id=([a-zA-Z0-9\-]+)\s+action=(\w+)",
    re.IGNORECASE,
)


@dataclass
class SopRunState:
    run_id: str
    project_id: str
    phase: str
    created_at: str
    updated_at: str
    reply_stream: str = ""
    reply_topic: str = ""
    window_days: int = 7
    include_audit: bool = True
    focus: str = "blocked"
    scope: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
    report_markdown: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "phase": self.phase,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reply_stream": self.reply_stream,
            "reply_topic": self.reply_topic,
            "window_days": self.window_days,
            "include_audit": self.include_audit,
            "focus": self.focus,
            "scope": self.scope,
            "artifacts": self.artifacts,
            "report_markdown": self.report_markdown,
            "pipeline": PIPELINE,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SopRunState":
        return cls(
            run_id=str(data["run_id"]),
            project_id=str(data["project_id"]),
            phase=str(data.get("phase") or "hitl_a"),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            reply_stream=str(data.get("reply_stream") or ""),
            reply_topic=str(data.get("reply_topic") or ""),
            window_days=int(data.get("window_days") or 7),
            include_audit=bool(data.get("include_audit", True)),
            focus=str(data.get("focus") or "blocked"),
            scope=dict(data.get("scope") or {}),
            artifacts=dict(data.get("artifacts") or {}),
            report_markdown=str(data.get("report_markdown") or ""),
        )


def matches_progress_sop(text: str) -> bool:
    return bool(_TRIGGER_RE.search(text or "")) or bool(_RESUME_RE.search(text or "")) or bool(
        _FOLLOWUP_RE.search(text or "")
    )


class ProgressSopWorkflow:
    """Deterministic orchestrator for progress-sop."""

    def __init__(
        self,
        *,
        settings: TraceForgeSettings | None = None,
        project_client: ProjectAdminClient | None = None,
        todo_workflow: TodoWorkflow | None = None,
        zulip_client: ZulipApiClient | None = None,
        audit_service: ProgressAuditService | None = None,
        runs_dir: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.project_client = project_client or ProjectAdminClient(self.settings)
        self.todo_workflow = todo_workflow
        self.zulip_client = zulip_client or ZulipApiClient(self.settings)
        self.audit_service = audit_service or ProgressAuditService(self.settings)
        data_root = Path(self.settings.traceforge_db_path).expanduser().resolve().parent
        self.runs_dir = runs_dir or (data_root / "sop_runs")
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.repo_root = Path(__file__).resolve().parents[3]
        self.bot_name = self.settings.zulip_bot_name or "Jarvis"

    def handle_request(self, request: AgentRequest) -> GatewayResponse:
        text = str(request.event.payload.get("text") or "")
        follow = _FOLLOWUP_RE.search(text)
        if follow:
            return self._handle_followup(request, follow.group(1), follow.group(2))
        resume = _RESUME_RE.search(text)
        if resume:
            return self._resume(
                request,
                run_id=resume.group(1),
                window_days=int(resume.group(2)),
                include_audit=resume.group(3) == "1",
                focus=resume.group(4),
            )
        trigger = _TRIGGER_RE.search(text)
        if not trigger:
            return GatewayResponse(
                request_id=request.request_id,
                run_id=None,
                reply_text="未识别为 progress-sop 触发语。示例：`@Jarvis 项目进度：todo-show`",
                status=RunStatus.FAILED,
                evidence=[{"type": "progress-sop", "ok": False, "reason": "no_trigger"}],
            )
        return self._start(request, project_id=trigger.group(1).strip().lower())

    def agent_send(self, to_agent: str, payload: dict[str, Any]) -> ToolResult:
        if to_agent != "gitea-audit":
            return ToolResult(
                tool_name="agent.send",
                ok=False,
                error=f"unsupported target agent: {to_agent}",
            )
        packet = dict(payload.get("packet") or {})
        if payload.get("project_id"):
            packet.setdefault("project_id", payload["project_id"])
        if payload.get("run_id"):
            packet.setdefault("run_id", payload["run_id"])
        if payload.get("text") and "docs_md" not in packet:
            packet.setdefault("discussion_md", str(payload["text"]))
        result = self.audit_service.handle(packet)
        return ToolResult(
            tool_name="agent.send",
            ok=True,
            data={"markdown": result.markdown, "session_key": result.session_key},
            evidence=result.evidence,
        )

    def _start(self, request: AgentRequest, *, project_id: str) -> GatewayResponse:
        evidence: list[dict[str, Any]] = [{"type": "progress-sop", "phase": "scope", "project_id": project_id}]
        try:
            project = self.project_client.resolve(project_id=project_id)
        except ProjectAdminError as exc:
            return GatewayResponse(
                request_id=request.request_id,
                run_id=None,
                reply_text=(
                    f"## progress-sop · Scope 失败\n"
                    f"无法从 **Project Admin** 解析项目 `{project_id}`。\n\n"
                    f"- 错误：{exc}\n"
                    f"- 请先在 Project Admin 建好项目名片（`projects` 表），再重试。"
                ),
                status=RunStatus.FAILED,
                evidence=[*evidence, {"type": "project.resolve", "ok": False, "error": str(exc)}],
            )

        now = _now()
        run_id = str(uuid4())
        stream, topic = _reply_location(request.event, project)
        state = SopRunState(
            run_id=run_id,
            project_id=project_id,
            phase="hitl_a",
            created_at=now,
            updated_at=now,
            reply_stream=stream,
            reply_topic=topic,
            window_days=int(project.get("window_days") or 7),
            scope={"project": project},
        )
        self._save(state)
        widget = self._hitl_a_widget(run_id=run_id, project=project)
        reply = (
            f"## progress-sop · Scope 完成：`{project.get('display_name') or project_id}`\n"
            f"- project_id：`{project_id}`（来自 Project Admin DB）\n"
            f"- Zulip：#{project.get('zulip_stream') or '—'}/{project.get('zulip_topic') or '—'}\n"
            f"- docs：`{project.get('docs_root') or '—'}`\n"
            f"- Todo subtree：`{project.get('subtree_code') or '—'}`\n"
            f"- Gitea：`{project.get('gitea_owner') or '—'}/{project.get('gitea_repo') or '—'}`\n"
            f"- 默认窗口：{state.window_days} 天\n"
            f"- run_id：`{run_id}`\n\n"
            f"请用下方按钮确认范围后继续（HITL-A）。"
        )
        evidence.extend(
            [
                {"type": "project.resolve", "ok": True, "project_id": project_id, "source": "project-admin"},
                {"type": "progress-sop", "phase": "hitl_a", "run_id": run_id},
            ]
        )
        return GatewayResponse(
            request_id=request.request_id,
            run_id=run_id,
            reply_text=reply,
            status=RunStatus.SUCCEEDED,
            evidence=evidence,
            widget_content=widget,
        )

    def _resume(
        self,
        request: AgentRequest,
        *,
        run_id: str,
        window_days: int,
        include_audit: bool,
        focus: str,
    ) -> GatewayResponse:
        state = self._load(run_id)
        if state is None:
            return GatewayResponse(
                request_id=request.request_id,
                run_id=run_id,
                reply_text=f"找不到 progress-sop run `{run_id}`，请重新触发：`项目进度：<project_id>`",
                status=RunStatus.FAILED,
                evidence=[{"type": "progress-sop", "ok": False, "reason": "missing_run"}],
            )
        state.window_days = window_days
        state.include_audit = include_audit
        state.focus = focus
        state.phase = "running"
        state.updated_at = _now()
        self._save(state)

        project = state.scope.get("project") or {}
        evidence: list[dict[str, Any]] = [
            {
                "type": "progress-sop",
                "phase": "resume",
                "run_id": run_id,
                "window_days": window_days,
                "include_audit": include_audit,
                "focus": focus,
            }
        ]

        docs_md = self._step_docs(project)
        state.artifacts["docs.md"] = docs_md
        evidence.append({"type": "progress-sop.step", "name": "docs", "ok": True})

        discussion_md = self._step_discussion(project)
        state.artifacts["discussion.md"] = discussion_md
        evidence.append({"type": "progress-sop.step", "name": "discussion", "ok": True})

        tasks_md = self._step_tasks(request.event, project)
        state.artifacts["tasks.md"] = tasks_md
        evidence.append({"type": "progress-sop.step", "name": "tasks", "ok": True})

        audit_md = "_已跳过 Audit（用户选择）_"
        if include_audit:
            send = self.agent_send(
                "gitea-audit",
                {
                    "project_id": state.project_id,
                    "run_id": state.run_id,
                    "packet": {
                        "project_id": state.project_id,
                        "run_id": state.run_id,
                        "project": project,
                        "docs_md": docs_md,
                        "discussion_md": discussion_md,
                        "tasks_md": tasks_md,
                    },
                },
            )
            audit_md = str((send.data or {}).get("markdown") or send.error or "Audit 失败")
            evidence.extend(send.evidence)
            evidence.append({"type": "progress-sop.step", "name": "audit", "ok": send.ok})
        else:
            evidence.append({"type": "progress-sop.step", "name": "audit", "ok": True, "skipped": True})
        state.artifacts["audit.md"] = audit_md

        report = self._build_report(state, project, focus=focus)
        state.artifacts["report.md"] = report
        state.report_markdown = report
        state.phase = "hitl_b"
        state.updated_at = _now()
        self._save(state)
        self._persist_run_files(state)
        self._try_save_report(state, project)

        widget = self._hitl_b_widget(run_id=state.run_id)
        evidence.append({"type": "progress-sop", "phase": "hitl_b", "run_id": state.run_id})
        return GatewayResponse(
            request_id=request.request_id,
            run_id=state.run_id,
            reply_text=report + "\n\n---\n请选择后续动作（HITL-B）：",
            status=RunStatus.SUCCEEDED,
            evidence=evidence,
            widget_content=widget,
        )

    def _handle_followup(self, request: AgentRequest, run_id: str, action: str) -> GatewayResponse:
        state = self._load(run_id)
        if state is None:
            return GatewayResponse(
                request_id=request.request_id,
                run_id=run_id,
                reply_text=f"找不到 run `{run_id}`。",
                status=RunStatus.FAILED,
            )
        action = action.lower()
        if action == "noop":
            state.phase = "done"
            state.updated_at = _now()
            self._save(state)
            return GatewayResponse(
                request_id=request.request_id,
                run_id=run_id,
                reply_text="已结束本轮 progress-sop（仅阅览报告）。",
                status=RunStatus.SUCCEEDED,
                evidence=[{"type": "progress-sop", "phase": "done", "action": "noop"}],
            )
        if action == "decision":
            path = self.repo_root / "workspace" / "memory" / "DECISION.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            stamp = _now()
            block = (
                f"\n\n## {stamp} · progress-sop `{state.project_id}`\n"
                f"- run_id: `{run_id}`\n"
                f"- focus: {state.focus}\n"
                f"- window_days: {state.window_days}\n"
            )
            with path.open("a", encoding="utf-8") as fh:
                fh.write(block)
            state.phase = "done"
            state.updated_at = _now()
            self._save(state)
            return GatewayResponse(
                request_id=request.request_id,
                run_id=run_id,
                reply_text=f"已写入决策摘记到 `workspace/memory/DECISION.md`（run `{run_id}`）。",
                status=RunStatus.SUCCEEDED,
                evidence=[{"type": "progress-sop", "phase": "done", "action": "decision"}],
            )
        if action == "todo":
            if self.todo_workflow is None:
                return GatewayResponse(
                    request_id=request.request_id,
                    run_id=run_id,
                    reply_text="Todo 工作流未注入，无法自动建建议任务。请手动创建 Todo。",
                    status=RunStatus.FAILED,
                )
            project = state.scope.get("project") or {}
            title = f"[progress-sop] 跟进 {project.get('display_name') or state.project_id}"
            command = TodoCommand(
                action=TodoAction.CREATE,
                raw_text=title,
                title=title,
                description=f"来自 progress-sop run {run_id}；focus={state.focus}",
                subtree_code=str(project.get("subtree_code") or "") or None,
                topic=str(project.get("zulip_topic") or state.reply_topic or "") or None,
            )
            # Prefer first owner/pm as assignee hint via description only; create may need assignee.
            members = project.get("members") if isinstance(project.get("members"), list) else []
            assignee = ""
            for member in members:
                if isinstance(member, dict) and member.get("role") in {"owner", "pm", "dev"}:
                    assignee = str(member.get("person_name") or "")
                    if assignee:
                        break
            create_cmd = TodoCommand(
                action=TodoAction.CREATE,
                raw_text=command.raw_text,
                title=command.title,
                description=command.description,
                assignee_name=assignee or None,
                subtree_code=command.subtree_code,
                topic=command.topic,
            )
            result = self.todo_workflow.handle(request.event, create_cmd)
            state.phase = "done"
            state.updated_at = _now()
            self._save(state)
            reply = getattr(result, "reply_text", None) or str(result)
            return GatewayResponse(
                request_id=request.request_id,
                run_id=run_id,
                reply_text=f"HITL-B 建 Todo：\n\n{reply}",
                status=RunStatus.SUCCEEDED,
                evidence=[{"type": "progress-sop", "phase": "done", "action": "todo"}],
            )
        return GatewayResponse(
            request_id=request.request_id,
            run_id=run_id,
            reply_text=f"未知 followup action：{action}",
            status=RunStatus.FAILED,
        )

    def _step_docs(self, project: dict[str, Any]) -> str:
        docs_root = str(project.get("docs_root") or "").strip()
        if not docs_root:
            return "_未配置 docs_root_"
        root = Path(docs_root)
        if not root.is_absolute():
            root = (self.repo_root / docs_root).resolve()
        parts: list[str] = [f"docs_root: `{docs_root}`"]
        for rel in (project.get("prd_path") or "PRD.md", project.get("tech_path") or "TECH.md", "STATUS.md"):
            path = root / Path(str(rel)).name
            if path.exists():
                body = path.read_text(encoding="utf-8").strip()
                parts.append(f"### {path.name}\n{body[:3000]}")
            else:
                parts.append(f"### {Path(str(rel)).name}\n_缺失_")
        return "\n\n".join(parts)

    def _step_discussion(self, project: dict[str, Any]) -> str:
        stream = str(project.get("zulip_stream") or "").strip()
        topic = str(project.get("zulip_topic") or "").strip()
        if not stream or not topic:
            return "_项目未绑定 Zulip stream/topic_"
        try:
            messages = self.zulip_client.fetch_topic_messages_all(stream=stream, topic=topic)
        except Exception as exc:  # noqa: BLE001
            return f"_拉取 Topic 失败：{type(exc).__name__}: {exc}_"
        if not messages:
            return f"_#{stream}/{topic} 暂无消息_"
        recent = messages[-30:]
        lines = [f"#{stream} / {topic} · 共 {len(messages)} 条，展示最近 {len(recent)} 条："]
        for msg in recent:
            stamp = msg.timestamp.strftime("%m-%d %H:%M")
            lines.append(f"- [{stamp}] {msg.sender_name}: {msg.content[:200]}")
        return "\n".join(lines)

    def _step_tasks(self, event: WorkspaceEvent, project: dict[str, Any]) -> str:
        if self.todo_workflow is None:
            return "_Todo 工作流未注入_"
        subtree = str(project.get("subtree_code") or "").strip()
        topic = str(project.get("zulip_topic") or event.location.topic or "").strip()
        command = TodoCommand(
            action=TodoAction.SUMMARY,
            raw_text="progress-sop tasks",
            topic=topic or None,
            subtree_code=subtree or None,
        )
        try:
            result = self.todo_workflow.handle(event, command)
            return getattr(result, "reply_text", None) or str(result)
        except Exception as exc:  # noqa: BLE001
            # fallback list
            try:
                list_cmd = TodoCommand(
                    action=TodoAction.LIST,
                    raw_text="progress-sop tasks",
                    topic=topic or None,
                    subtree_code=subtree or None,
                )
                result = self.todo_workflow.handle(event, list_cmd)
                return getattr(result, "reply_text", None) or str(result)
            except Exception as exc2:  # noqa: BLE001
                return f"_Todo 汇总失败：{type(exc).__name__}/{type(exc2).__name__}_"

    def _build_report(self, state: SopRunState, project: dict[str, Any], *, focus: str) -> str:
        members = project.get("members") if isinstance(project.get("members"), list) else []
        owner_line = ", ".join(
            str(m.get("person_name"))
            for m in members
            if isinstance(m, dict) and m.get("person_name")
        ) or "—"
        return (
            f"## 项目进度体检：{project.get('display_name') or state.project_id}"
            f"（`{state.project_id}`）\n"
            f"- 流水线：`{PIPELINE}`\n"
            f"- 范围：#{project.get('zulip_stream') or '—'} / {project.get('zulip_topic') or '—'}"
            f" · 近 {state.window_days} 天\n"
            f"- 负责人：{owner_line}\n"
            f"- 侧重点：{focus}\n"
            f"- 是否含 Audit：{'是' if state.include_audit else '否'}\n"
            f"- 生成时间：{state.updated_at}\n"
            f"- run_id：`{state.run_id}`\n\n"
            f"### 文档\n{state.artifacts.get('docs.md', '_无_')}\n\n"
            f"### 讨论\n{state.artifacts.get('discussion.md', '_无_')}\n\n"
            f"### 任务\n{state.artifacts.get('tasks.md', '_无_')}\n\n"
            f"### 审查（RepoAudit）\n{state.artifacts.get('audit.md', '_无_')}\n\n"
            f"### 综合判断\n"
            f"- 状态：已生成体检报告（代码仍由人完成）\n"
            f"- 建议下一步：对照审查缺口收敛 Todo，或记录 DECISION\n"
        )

    def _hitl_a_widget(self, *, run_id: str, project: dict[str, Any]) -> dict[str, Any]:
        default_window = int(project.get("window_days") or 7)
        bot = self.bot_name
        choices = [
            {
                "short_name": f"{default_window}天+审",
                "long_name": f"窗口 {default_window} 天，含 RepoAudit",
                "reply": f"@{bot} sop continue run_id={run_id} window={default_window} include_audit=1 focus=blocked",
            },
            {
                "short_name": "14天+审",
                "long_name": "窗口 14 天，含 RepoAudit",
                "reply": f"@{bot} sop continue run_id={run_id} window=14 include_audit=1 focus=docs",
            },
            {
                "short_name": "7天无审",
                "long_name": "窗口 7 天，跳过 Audit",
                "reply": f"@{bot} sop continue run_id={run_id} window=7 include_audit=0 focus=blocked",
            },
        ]
        return build_zform_choices(heading="确认 progress-sop 范围", choices=choices)

    def _hitl_b_widget(self, *, run_id: str) -> dict[str, Any]:
        bot = self.bot_name
        choices = [
            {
                "short_name": "仅阅览",
                "long_name": "结束，不写 Todo",
                "reply": f"@{bot} sop followup run_id={run_id} action=noop",
            },
            {
                "short_name": "建Todo",
                "long_name": "按报告建一条跟进 Todo",
                "reply": f"@{bot} sop followup run_id={run_id} action=todo",
            },
            {
                "short_name": "记决策",
                "long_name": "写入 DECISION.md",
                "reply": f"@{bot} sop followup run_id={run_id} action=decision",
            },
        ]
        return build_zform_choices(heading="报告后续动作", choices=choices)

    def _persist_run_files(self, state: SopRunState) -> None:
        out = self.repo_root / "workspace_shared" / "runs" / state.run_id
        out.mkdir(parents=True, exist_ok=True)
        for name, body in state.artifacts.items():
            (out / name).write_text(body, encoding="utf-8")
        (out / "scope.json").write_text(
            json.dumps(state.scope, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _try_save_report(self, state: SopRunState, project: dict[str, Any]) -> None:
        try:
            self.project_client.create_report(
                project_id=state.project_id,
                title=f"progress-sop {state.project_id} {state.updated_at}",
                markdown_body=state.report_markdown,
                pipeline=PIPELINE,
                meta_json={
                    "run_id": state.run_id,
                    "window_days": state.window_days,
                    "include_audit": state.include_audit,
                    "focus": state.focus,
                },
                mentor=self.settings.project_admin_mentor,
            )
        except Exception:
            # Report persistence is best-effort for demo.
            return

    def _save(self, state: SopRunState) -> None:
        path = self.runs_dir / f"{state.run_id}.json"
        path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load(self, run_id: str) -> SopRunState | None:
        path = self.runs_dir / f"{run_id}.json"
        if not path.exists():
            return None
        return SopRunState.from_dict(json.loads(path.read_text(encoding="utf-8")))


class ProgressSopHandler:
    """Gateway handler: progress-sop first, else delegate to inner agent runtime."""

    def __init__(self, inner: Any, workflow: ProgressSopWorkflow) -> None:
        self.inner = inner
        self.workflow = workflow

    def handle(self, request: AgentRequest) -> GatewayResponse:
        text = str(request.event.payload.get("text") or "")
        if matches_progress_sop(text):
            return self.workflow.handle_request(request)
        return self.inner.handle(request)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _reply_location(event: WorkspaceEvent, project: dict[str, Any]) -> tuple[str, str]:
    stream = (
        event.location.channel_name
        or str(project.get("zulip_stream") or "")
        or "general"
    )
    topic = event.location.topic or str(project.get("zulip_topic") or "progress-sop")
    return stream, topic
