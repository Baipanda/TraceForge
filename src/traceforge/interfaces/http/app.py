from __future__ import annotations

import json
import logging
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from pathlib import Path

from traceforge.agent.harness import PromptHarness
from traceforge.agent.runtime import AgentRuntime
from traceforge.agents import (
    AgentRouter,
    load_agents_config,
    resolve_sessions_root,
    resolve_workspace_root,
)
from traceforge.application.gitea_audit_agent import GiteaAuditAgent
from traceforge.application.process_event import ProcessWorkspaceEvent
from traceforge.config import get_settings
from traceforge.gateway.workspace_gateway import WorkspaceGateway
from traceforge.infrastructure.llm.deepseek import DeepSeekClient
from traceforge.interfaces.gitea.normalizer import normalize_gitea_webhook
from traceforge.interfaces.gitea.signature import verify_gitea_signature
from traceforge.interfaces.zulip.normalizer import normalize_zulip_payload
from traceforge.memory.markdown_index import MarkdownMemoryIndex
from traceforge.memory.markdown_store import MarkdownMemoryStore
from traceforge.session.transcript import JsonlSessionStore
from traceforge.tools.todo_tools import build_default_tool_registry

logger = logging.getLogger(__name__)

_processor = ProcessWorkspaceEvent()
_settings = get_settings()
_agents_config = load_agents_config(_settings.agents_config_path or None)
_agent_router = AgentRouter(_agents_config)
_model = DeepSeekClient(_settings) if _settings.llm_enabled else None
_runtime = AgentRuntime(
    harness=PromptHarness(memory_store=_processor.memory_store),
    tool_registry=_processor.tool_registry,
    model=_model,
    max_model_turns=_settings.agent_max_model_turns,
    max_tool_calls=_settings.agent_max_tool_calls,
)
_gateway = WorkspaceGateway(
    handler=_runtime,
    session_recorder=_processor.repository.record_session,
    memory_store=_processor.memory_store,
    memory_index=_processor.memory_index,
    session_summarizer=_model,
    keep_recent_tokens=_settings.session_keep_recent_tokens,
)
_gitea_audit_agent = GiteaAuditAgent(settings=_settings, agents_config=_agents_config)
_gateways: dict[str, WorkspaceGateway] = {"main": _gateway}


def _gateway_for(agent_id: str) -> WorkspaceGateway:
    if agent_id in _gateways:
        return _gateways[agent_id]
    entry = _agents_config.get(agent_id)
    workspace_root = resolve_workspace_root(entry)
    data_root = Path(_settings.traceforge_db_path).expanduser().resolve().parent
    session_root = resolve_sessions_root(entry, data_root=data_root)
    memory_store = MarkdownMemoryStore(workspace_root)
    memory_index = MarkdownMemoryIndex(_processor.repository.db_path, memory_store)
    # Expert agents share the default tool registry for now; narrow later via entry.tools.
    runtime = AgentRuntime(
        harness=PromptHarness(workspace_root=workspace_root, memory_store=memory_store),
        tool_registry=build_default_tool_registry(
            _processor.repository,
            memory_index=memory_index,
        ),
        model=_model,
        max_model_turns=_settings.agent_max_model_turns,
        max_tool_calls=_settings.agent_max_tool_calls,
    )
    gateway = WorkspaceGateway(
        handler=runtime,
        session_store=JsonlSessionStore(session_root),
        session_recorder=_processor.repository.record_session,
        memory_store=memory_store,
        memory_index=memory_index,
        session_summarizer=_model,
        keep_recent_tokens=_settings.session_keep_recent_tokens,
    )
    _gateways[agent_id] = gateway
    return gateway


async def homepage(_: Request) -> PlainTextResponse:
    return PlainTextResponse("TraceForge is running.\n")


async def health(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": "traceforge",
            "status": "healthy",
            "agents": sorted(_agents_config.agents.keys()),
            "default_agent": _agents_config.default_agent_id(),
        }
    )


async def ingest_zulip_event(request: Request) -> JSONResponse:
    payload = await _json_body(request)
    event = normalize_zulip_payload(payload)
    # Prefer explicit delivery agent_id from bridge, else bindings.
    delivery = event.payload.get("delivery") if isinstance(event.payload.get("delivery"), dict) else {}
    hinted = str(delivery.get("agent_id") or "").strip()
    agent_id = hinted if hinted in _agents_config.agents else _agent_router.resolve(event)
    gateway = _gateway_for(agent_id)
    result = gateway.route(event)
    return JSONResponse(
        {
            "ok": True,
            "agent_id": agent_id,
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


async def ingest_gitea_event(request: Request) -> JSONResponse:
    """Gitea webhook → audit log + RepoAudit Zulip notify (no AgentRuntime yet)."""
    raw = await request.body()
    signature = request.headers.get("X-Gitea-Signature") or request.headers.get(
        "X-Hub-Signature-256"
    )
    if not verify_gitea_signature(
        body=raw,
        secret=_settings.gitea_webhook_secret,
        signature_header=signature,
    ):
        return JSONResponse({"ok": False, "error": "invalid signature"}, status_code=401)

    event_type = (request.headers.get("X-Gitea-Event") or "").strip().lower()
    delivery_id = (request.headers.get("X-Gitea-Delivery") or "").strip() or None

    if event_type == "ping" or not raw:
        return JSONResponse({"ok": True, "ignored": True, "reason": "ping"})

    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "body must be object"}, status_code=400)

    # Gitea sometimes sends ping without X-Gitea-Event in tests; also ignore empty hooks.
    if payload.get("zen") is not None and not payload.get("repository"):
        return JSONResponse({"ok": True, "ignored": True, "reason": "ping"})

    audit_event = normalize_gitea_webhook(
        payload, event_type=event_type or None, delivery_id=delivery_id
    )
    if audit_event is None:
        return JSONResponse(
            {"ok": True, "ignored": True, "reason": "unsupported_or_empty", "event_type": event_type}
        )

    try:
        result = _gitea_audit_agent.handle(audit_event, raw_payload=payload)
    except Exception as exc:
        logger.exception("gitea-audit agent failed")
        return JSONResponse(
            {"ok": False, "error": str(exc), "event_type": audit_event.event_type},
            status_code=502,
        )

    notify = result.notify
    return JSONResponse(
        {
            "ok": True,
            "agent_id": result.agent_id,
            "session_key": result.session_key,
            "event_type": audit_event.event_type,
            "repository": audit_event.repository,
            "notified": notify.notified,
            "zulip_message_id": notify.zulip_message_id,
            "audit_path": notify.audit_path,
            "skipped_reason": notify.skipped_reason,
            "checked_files": result.checked_files,
            "findings_count": result.findings_count,
            "preview": notify.message,
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
        Route("/api/events/gitea", ingest_gitea_event, methods=["POST"]),
    ],
)
