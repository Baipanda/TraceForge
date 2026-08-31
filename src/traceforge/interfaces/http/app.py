from __future__ import annotations

import json
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from traceforge.agent.harness import PromptHarness
from traceforge.agent.runtime import AgentRuntime
from traceforge.application.process_event import ProcessWorkspaceEvent
from traceforge.config import get_settings
from traceforge.gateway.workspace_gateway import WorkspaceGateway
from traceforge.infrastructure.llm.deepseek import DeepSeekClient
from traceforge.infrastructure.storage.memory_repository import SqliteMemoryRepository
from traceforge.memory.service import MemoryService
from traceforge.interfaces.zulip.normalizer import normalize_zulip_payload


_processor = ProcessWorkspaceEvent()
_settings = get_settings()
_memory_repository = SqliteMemoryRepository(_settings.traceforge_db_path)
_memory_service = MemoryService(_memory_repository, search_limit=_settings.memory_search_limit)
_model = DeepSeekClient(_settings) if _settings.llm_enabled else None
_runtime = AgentRuntime(
    harness=PromptHarness(),
    tool_registry=_processor.tool_registry,
    model=_model,
    max_model_turns=_settings.agent_max_model_turns,
    max_tool_calls=_settings.agent_max_tool_calls,
)
_gateway = WorkspaceGateway(
    handler=_runtime,
    session_recorder=_processor.repository.record_session,
    memory_service=_memory_service if _settings.memory_enabled else None,
    keep_recent_tokens=_settings.session_keep_recent_tokens,
)


async def homepage(_: Request) -> PlainTextResponse:
    return PlainTextResponse("TraceForge is running.\n")


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "traceforge", "status": "healthy"})


async def ingest_zulip_event(request: Request) -> JSONResponse:
    payload = await _json_body(request)
    event = normalize_zulip_payload(payload)
    result = _gateway.route(event)
    return JSONResponse(
        {
            "ok": True,
            "event": {
                "id": event.event_id,
                "route_key": event.route_key(),
                "external_event_id": event.external_event_id,
            },
            "result": {
                "intent": _intent_from_evidence(result.evidence),
                "reply_text": result.reply_text,
                "evidence": result.evidence,
            },
        }
    )


def _intent_from_evidence(evidence: list[dict[str, Any]]) -> str:
    for item in evidence:
        if item.get("type") == "intent":
            action = item.get("action")
            if isinstance(action, str):
                return f"todo.{action}" if action != "unknown" else action
    for item in evidence:
        if item.get("type") == "tool_call":
            tool_name = item.get("tool_name")
            if isinstance(tool_name, str) and tool_name.startswith("todo."):
                return tool_name
    return "agent"


async def _json_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("request body must be JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object")
    return data


app = Starlette(
    debug=True,
    routes=[
        Route("/", homepage, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/api/events/zulip", ingest_zulip_event, methods=["POST"]),
    ],
)
