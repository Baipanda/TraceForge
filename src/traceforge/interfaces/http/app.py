from __future__ import annotations

import json
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from traceforge.application.process_event import ProcessWorkspaceEvent
from traceforge.interfaces.zulip.normalizer import normalize_zulip_payload


async def homepage(_: Request) -> PlainTextResponse:
    return PlainTextResponse("TraceForge is running.\n")


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "traceforge", "status": "healthy"})


async def ingest_zulip_event(request: Request) -> JSONResponse:
    payload = await _json_body(request)
    event = normalize_zulip_payload(payload)
    result = ProcessWorkspaceEvent().execute(event)
    return JSONResponse(
        {
            "ok": True,
            "event": {
                "id": event.event_id,
                "route_key": event.route_key(),
                "external_event_id": event.external_event_id,
            },
            "result": {
                "intent": result.intent,
                "reply_text": result.reply_text,
                "evidence": result.evidence,
            },
        }
    )


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
