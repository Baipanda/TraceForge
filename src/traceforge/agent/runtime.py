from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from traceforge.agent.harness import PromptHarness
from traceforge.agent.models import AgentRequest, AgentRun, GatewayResponse, RunStatus, RunStep, StepKind
from traceforge.tools.registry import ToolRegistry


class ChatModel(Protocol):
    def complete(self, system_prompt: str, messages: list[dict[str, str]]) -> str:
        ...


class AgentRuntime:
    """TraceForge agent loop boundary.

    The runtime owns one run at a time: assemble prompt, call the model, call tools,
    and produce an auditable final answer. The current implementation is a small
    skeleton so the architecture is explicit before we connect real tool calling.
    """

    def __init__(
        self,
        *,
        harness: PromptHarness | None = None,
        tool_registry: ToolRegistry | None = None,
        model: ChatModel | None = None,
    ) -> None:
        self.harness = harness or PromptHarness()
        self.tool_registry = tool_registry or ToolRegistry()
        self.model = model

    def handle(self, request: AgentRequest) -> GatewayResponse:
        run = AgentRun(request=request, status=RunStatus.RUNNING)
        tool_schemas = self.tool_registry.list_schemas()
        bundle = self.harness.build(request, tool_schemas=tool_schemas)
        run.steps.append(
            RunStep(
                kind=StepKind.MODEL,
                status=RunStatus.SUCCEEDED,
                input={
                    "messages": bundle.messages,
                    "skills": bundle.skills,
                    "tools": [tool["name"] for tool in bundle.tools],
                },
                output={"system_prompt_chars": len(bundle.system_prompt)},
                finished_at=datetime.now(timezone.utc),
            )
        )

        if self.model is None:
            final_text = self._fallback_reply(bundle.skills)
        else:
            final_text = self.model.complete(bundle.system_prompt, bundle.messages)

        run.final_text = final_text
        run.status = RunStatus.SUCCEEDED
        run.finished_at = datetime.now(timezone.utc)
        run.steps.append(
            RunStep(
                kind=StepKind.FINAL,
                status=RunStatus.SUCCEEDED,
                output=final_text,
                finished_at=run.finished_at,
            )
        )
        return GatewayResponse(
            request_id=request.request_id,
            run_id=run.run_id,
            reply_text=final_text,
            status=run.status,
            evidence=[
                {
                    "type": "agent_run",
                    "run_id": run.run_id,
                    "skills": bundle.skills,
                }
            ],
        )

    def _fallback_reply(self, skills: list[str]) -> str:
        if skills:
            return f"TraceForge Runtime 已识别可用 Skill：{', '.join(skills)}。下一步会接入模型与工具调用。"
        return "TraceForge Runtime 已接收请求。下一步会接入模型、Skills 和工具调用。"
