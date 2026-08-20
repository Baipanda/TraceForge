from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol

from traceforge.agent.harness import PromptHarness
from traceforge.agent.models import (
    AgentRequest,
    AgentRun,
    ContextItem,
    GatewayResponse,
    ModelTurn,
    ModelToolCall,
    PromptBundle,
    RunStatus,
    RunStep,
    StepKind,
)
from traceforge.tools.models import ToolCall, ToolResult
from traceforge.tools.registry import ToolRegistry


class ChatModel(Protocol):
    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> ModelTurn:
        ...


class AgentRuntime:
    """TraceForge agent loop boundary.

    The runtime owns one run at a time: assemble prompt, call the model, call tools,
    and produce an auditable final answer. Tool calls are provider-adapted before
    execution and ToolResults are fed back into the next model turn.
    """

    def __init__(
        self,
        *,
        harness: PromptHarness | None = None,
        tool_registry: ToolRegistry | None = None,
        model: ChatModel | None = None,
        max_steps: int | None = None,
        max_model_turns: int = 8,
        max_tool_calls: int = 12,
    ) -> None:
        self.harness = harness or PromptHarness()
        self.tool_registry = tool_registry or ToolRegistry()
        self.model = model
        # max_steps is kept as a compatibility alias for the first Runtime API.
        self.max_model_turns = max_steps if max_steps is not None else max_model_turns
        self.max_tool_calls = max_tool_calls

    def handle(self, request: AgentRequest) -> GatewayResponse:
        run = AgentRun(request=request, status=RunStatus.RUNNING)
        tool_schemas = self.tool_registry.list_schemas()
        model_tool_schemas, tool_name_map = _model_tool_schemas(tool_schemas)
        bundle = self.harness.build(
            request,
            context_items=_context_items_from_metadata(request.metadata.get("memory_context_items")),
            tool_schemas=model_tool_schemas,
        )
        messages = list(bundle.messages)
        evidence: list[dict[str, object]] = [
            {
                "type": "agent_run",
                "run_id": run.run_id,
                "skills": bundle.skills,
                "max_model_turns": self.max_model_turns,
                "max_tool_calls": self.max_tool_calls,
            }
        ]

        if self.model is None:
            final_text = self._fallback_reply(bundle.skills)
            evidence.append({"type": "model", "status": "disabled"})
        else:
            final_text = self._run_loop(
                run,
                request,
                bundle,
                messages,
                evidence,
                tool_name_map,
            )

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
            evidence=evidence,
        )

    def _run_loop(
        self,
        run: AgentRun,
        request: AgentRequest,
        bundle: PromptBundle,
        messages: list[dict[str, object]],
        evidence: list[dict[str, object]],
        tool_name_map: dict[str, str],
    ) -> str:
        system_prompt = bundle.system_prompt
        tools = bundle.tools
        tool_call_count = 0
        repeated_calls: dict[str, int] = {}

        for step_number in range(1, self.max_model_turns + 1):
            started_at = datetime.now(timezone.utc)
            if self.model is None:
                return "Runtime 未配置模型。"
            turn: ModelTurn = self.model.complete(system_prompt, messages, tools)
            finished_at = datetime.now(timezone.utc)
            run.steps.append(
                RunStep(
                    kind=StepKind.MODEL,
                    status=RunStatus.SUCCEEDED,
                    input={
                        "step": step_number,
                        "message_count": len(messages),
                        "skills": bundle.skills,
                        "tools": [tool["name"] for tool in tools],
                    },
                    output={
                        "content_chars": len(turn.content),
                        "tool_calls": [call.name for call in turn.tool_calls],
                    },
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )
            evidence.append(
                {
                    "type": "model_turn",
                    "step": step_number,
                    "tool_calls": [call.name for call in turn.tool_calls],
                }
            )

            if not turn.tool_calls:
                return turn.content.strip() or "模型没有生成可展示的回复。"

            messages.append(_assistant_tool_message(turn))
            for model_call in turn.tool_calls:
                actual_tool_name = tool_name_map.get(model_call.name, model_call.name)
                call_fingerprint = _tool_call_fingerprint(actual_tool_name, model_call.arguments)
                repeated_calls[call_fingerprint] = repeated_calls.get(call_fingerprint, 0) + 1
                tool_call_count += 1
                if tool_call_count > self.max_tool_calls:
                    tool_result = ToolResult(
                        tool_name=actual_tool_name,
                        ok=False,
                        error="本次请求的工具调用预算已用完，请根据已有结果回复用户。",
                        evidence=[{"type": "tool.budget_exhausted"}],
                        call_id=model_call.call_id,
                    )
                elif repeated_calls[call_fingerprint] > 2:
                    tool_result = ToolResult(
                        tool_name=actual_tool_name,
                        ok=False,
                        error="检测到重复的相同工具调用，请不要重复执行。",
                        evidence=[{"type": "tool.repeated_call_blocked"}],
                        call_id=model_call.call_id,
                    )
                else:
                    tool_result = self._execute_tool(request, model_call, tool_name_map)
                run.steps.append(
                    RunStep(
                        kind=StepKind.TOOL,
                        status=RunStatus.SUCCEEDED if tool_result.ok else RunStatus.FAILED,
                        input={
                            "call_id": model_call.call_id,
                            "tool_name": model_call.name,
                            "arguments": model_call.arguments,
                        },
                        output={
                            "ok": tool_result.ok,
                            "error": tool_result.error,
                            "evidence": tool_result.evidence,
                        },
                        finished_at=datetime.now(timezone.utc),
                    )
                )
                evidence.append(
                    {
                        "type": "tool_call",
                        "tool_name": tool_result.tool_name,
                        "model_tool_name": model_call.name,
                        "call_id": model_call.call_id,
                        "ok": tool_result.ok,
                        "evidence": tool_result.evidence,
                    }
                )
                messages.append(_tool_result_message(model_call.call_id, tool_result))

        return self._finalize_after_budget(run, system_prompt, messages, evidence)

    def _finalize_after_budget(
        self,
        run: AgentRun,
        system_prompt: str,
        messages: list[dict[str, object]],
        evidence: list[dict[str, object]],
    ) -> str:
        """Ask the model to summarize instead of exposing a raw loop-limit error."""

        if self.model is None:
            return "Agent 执行预算已用完，请缩小请求范围后重试。"
        try:
            turn = self.model.complete(
                system_prompt
                + "\n\n当前执行预算已用完。请只根据已有工具结果总结进展、明确未完成事项，"
                "不要再调用工具，也不要声称尚未完成的动作已经完成。",
                messages,
                tools=[],
            )
            run.steps.append(
                RunStep(
                    kind=StepKind.MODEL,
                    status=RunStatus.SUCCEEDED,
                    input={"purpose": "budget_finalize"},
                    output={"content_chars": len(turn.content)},
                    finished_at=datetime.now(timezone.utc),
                )
            )
            evidence.append({"type": "budget_finalize", "status": "used"})
            if turn.content.strip():
                return turn.content.strip()
        except Exception as exc:
            evidence.append(
                {"type": "budget_finalize", "status": "failed", "error": type(exc).__name__}
            )
        return "本次请求执行步骤较多，当前已暂停。已有动作结果已保留，请告诉我继续处理哪个未完成事项。"

    def _execute_tool(
        self,
        request: AgentRequest,
        call: ModelToolCall,
        tool_name_map: dict[str, str],
    ) -> ToolResult:
        arguments = dict(call.arguments)
        arguments.setdefault("workspace_id", request.event.location.workspace_id)
        arguments.setdefault("channel_id", request.event.location.channel_id)
        arguments.setdefault("channel_name", request.event.location.channel_name)
        arguments.setdefault("topic", request.event.location.topic)
        arguments.setdefault("source", request.event.source.value)
        arguments.setdefault("kind", request.event.kind.value)
        arguments.setdefault("actor_name", request.event.actor.display_name)
        arguments.setdefault("actor_email", request.event.actor.email)
        arguments.setdefault("actor_external_id", request.event.actor.external_id)
        arguments.setdefault("external_event_id", request.event.external_event_id)
        arguments.setdefault("raw_text", request.text)
        actual_tool_name = tool_name_map.get(call.name, call.name)
        try:
            return self.tool_registry.call(
                ToolCall(name=actual_tool_name, arguments=arguments, call_id=call.call_id)
            )
        except Exception as exc:
            return ToolResult(
                tool_name=actual_tool_name,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                evidence=[{"type": "tool.error", "tool_name": actual_tool_name}],
                call_id=call.call_id,
            )

    def _fallback_reply(self, skills: list[str]) -> str:
        if skills:
            return f"TraceForge Runtime 当前未配置模型，已加载 Skill：{', '.join(skills)}。"
        return "TraceForge Runtime 当前未配置模型，无法生成回复。"


def _assistant_tool_message(turn: ModelTurn) -> dict[str, object]:
    return {
        "role": "assistant",
        "content": turn.content,
        "tool_calls": [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in turn.tool_calls
        ],
    }


def _tool_result_message(call_id: str, result: ToolResult) -> dict[str, object]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(
            {
                "ok": result.ok,
                "data": result.data,
                "error": result.error,
                "evidence": result.evidence,
            },
            ensure_ascii=False,
            default=str,
        ),
    }


def _model_tool_schemas(
    schemas: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, str]]:
    """Adapt internal names such as ``todo.create`` to provider-safe names."""

    adapted: list[dict[str, object]] = []
    name_map: dict[str, str] = {}
    used_names: set[str] = set()
    for schema in schemas:
        internal_name = str(schema["name"])
        model_name = _provider_safe_tool_name(internal_name)
        base_name = model_name
        suffix = 2
        while model_name in used_names:
            model_name = f"{base_name}_{suffix}"
            suffix += 1
        used_names.add(model_name)
        name_map[model_name] = internal_name
        adapted.append({**schema, "name": model_name})
    return adapted, name_map


def _provider_safe_tool_name(name: str) -> str:
    return "".join(
        character if character.isalnum() or character in {"_", "-"} else "_"
        for character in name
    )


def _tool_call_fingerprint(name: str, arguments: dict[str, object]) -> str:
    return f"{name}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)}"


def _context_items_from_metadata(value: object) -> list[ContextItem] | None:
    if not isinstance(value, list):
        return None
    items: list[ContextItem] = []
    for item in value:
        if isinstance(item, ContextItem):
            items.append(item)
        elif isinstance(item, dict):
            source = str(item.get("source") or "memory")
            content = str(item.get("content") or "")
            metadata = item.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            items.append(ContextItem(source=source, content=content, metadata=metadata))
    return items or None
