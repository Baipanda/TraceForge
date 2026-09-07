"""Zulip interactive choice (zform) tools."""

from __future__ import annotations

import json
from typing import Any

from traceforge.config import TraceForgeSettings, get_settings
from traceforge.infrastructure.zulip.client import ZulipApiClient
from traceforge.tools.models import ToolResult
from traceforge.tools.registry import RegisteredTool, ToolRegistry


def build_zform_choices(
    *,
    heading: str,
    choices: list[dict[str, str]],
    numbered: bool = True,
) -> dict[str, Any]:
    """Build a Zulip zform widget.

    When ``numbered`` is True (default), the select control shows the full
    ``1. <explanation>`` label via ``short_name`` only. ``long_name`` is left
    empty — Zulip otherwise renders short_name + long_name side-by-side (duplicate).
    """
    normalized = []
    for index, item in enumerate(choices, start=1):
        short = str(item.get("short_name") or item.get("label") or "").strip()
        long = str(item.get("long_name") or item.get("description") or "").strip()
        reply = str(item.get("reply") or "").strip()
        if numbered:
            explanation = _strip_leading_index(long or short)
            label = f"{index}. {explanation}" if explanation else str(index)
            short = label
            long = ""
        normalized.append(
            {
                "type": "multiple_choice",
                "short_name": short,
                "long_name": long,
                "reply": reply,
            }
        )
    return {
        "widget_type": "zform",
        "extra_data": {
            "type": "choices",
            "heading": heading,
            "choices": normalized,
        },
    }


def format_numbered_menu(choices: list[dict[str, str]]) -> str:
    """Markdown menu lines mirroring Claude Code option list."""
    lines: list[str] = []
    for index, item in enumerate(choices, start=1):
        long = str(item.get("long_name") or item.get("description") or item.get("short_name") or "").strip()
        explanation = _strip_leading_index(long)
        lines.append(f"{index}. {explanation}" if explanation else f"{index}.")
    return "\n".join(lines)


def _strip_leading_index(text: str) -> str:
    text = (text or "").strip()
    if len(text) >= 2 and text[0].isdigit() and text[1] in {".", "、", ")", "］", "]"}:
        return text[2:].strip()
    if len(text) >= 3 and text[0].isdigit() and text[1].isdigit() and text[2] in {".", "、", ")"}:
        return text[3:].strip()
    return text


def register_zulip_choice_tools(
    registry: ToolRegistry,
    *,
    settings: TraceForgeSettings | None = None,
    zulip_client: ZulipApiClient | None = None,
) -> None:
    settings = settings or get_settings()
    client = zulip_client or ZulipApiClient(settings)

    def _send_choices(arguments: dict[str, Any]) -> ToolResult:
        stream = str(arguments.get("stream") or arguments.get("channel_name") or "").strip()
        topic = str(arguments.get("topic") or "").strip()
        content = str(arguments.get("content") or arguments.get("message") or "").strip()
        heading = str(arguments.get("heading") or "请选择").strip()
        raw_choices = arguments.get("choices")
        if isinstance(raw_choices, str):
            try:
                raw_choices = json.loads(raw_choices)
            except json.JSONDecodeError:
                return ToolResult(
                    tool_name="zulip.send_choices",
                    ok=False,
                    error="choices must be a JSON list",
                )
        if not stream or not topic or not content:
            return ToolResult(
                tool_name="zulip.send_choices",
                ok=False,
                error="stream, topic, and content are required",
            )
        if not isinstance(raw_choices, list) or not raw_choices:
            return ToolResult(
                tool_name="zulip.send_choices",
                ok=False,
                error="choices must be a non-empty list",
            )
        widget = build_zform_choices(heading=heading, choices=raw_choices)
        # Ensure bot can be triggered on click: reply should mention the bot.
        bot = settings.zulip_bot_name or "Jarvis"
        for choice in widget["extra_data"]["choices"]:
            reply = choice["reply"]
            if reply and f"@{bot}" not in reply and bot.lower() not in reply.lower():
                choice["reply"] = f"@{bot} {reply}"
        try:
            message_id = client.send_stream_message(
                stream=stream,
                topic=topic,
                content=content,
                widget_content=widget,
            )
        except Exception as exc:  # noqa: BLE001 - surface as tool error
            return ToolResult(
                tool_name="zulip.send_choices",
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                evidence=[{"type": "zulip.send_choices", "ok": False}],
            )
        return ToolResult(
            tool_name="zulip.send_choices",
            ok=True,
            data={"message_id": message_id, "widget_content": widget},
            evidence=[
                {
                    "type": "zulip.send_choices",
                    "ok": True,
                    "stream": stream,
                    "topic": topic,
                    "message_id": message_id,
                }
            ],
        )

    registry.register(
        RegisteredTool(
            name="zulip.send_choices",
            description=(
                "Send a Zulip zform multiple-choice widget so the user can click options. "
                "Use for HITL gates (approve/reject, pick window, next action). "
                "Each choice needs a description (long_name) and reply; "
                "options are auto-numbered 1/2/3 in the Zulip select box."
            ),
            schema={
                "type": "object",
                "properties": {
                    "stream": {"type": "string"},
                    "channel_name": {"type": "string"},
                    "topic": {"type": "string"},
                    "content": {"type": "string"},
                    "message": {"type": "string"},
                    "heading": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "short_name": {"type": "string"},
                                "long_name": {"type": "string"},
                                "reply": {"type": "string"},
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["topic", "choices"],
            },
            handler=_send_choices,
        )
    )
