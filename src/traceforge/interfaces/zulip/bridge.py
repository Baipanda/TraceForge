from __future__ import annotations

import base64
import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from traceforge.config import TraceForgeSettings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class ZulipTraceForgeBridge:
    settings: TraceForgeSettings = field(default_factory=get_settings)
    seen_message_ids: set[int] = field(default_factory=set)

    def run_forever(self) -> None:
        self._validate_settings()
        queue = self._register_queue()
        queue_id = queue["queue_id"]
        last_event_id = int(queue["last_event_id"])
        logger.info("Zulip bridge registered queue_id=%s last_event_id=%s", queue_id, last_event_id)

        while True:
            try:
                response = self._zulip_get(
                    "/api/v1/events",
                    {
                        "queue_id": queue_id,
                        "last_event_id": str(last_event_id),
                        "dont_block": "true",
                    },
                    timeout_seconds=30,
                )
                events = response.get("events", [])
                for event in events:
                    last_event_id = max(last_event_id, int(event.get("id", last_event_id)))
                    self._handle_event(event)
                if not events:
                    time.sleep(self.settings.zulip_poll_interval_seconds)
            except KeyboardInterrupt:
                logger.info("Zulip bridge stopped")
                return
            except Exception:
                logger.exception("Zulip bridge loop failed; retrying")
                time.sleep(5)

    def _register_queue(self) -> dict[str, Any]:
        return self._zulip_post(
            "/api/v1/register",
            {
                "event_types": json.dumps(["message"]),
                "all_public_streams": "true",
                "apply_markdown": "true",
            },
        )

    def _handle_event(self, event: dict[str, Any]) -> None:
        if event.get("type") != "message":
            return
        message = event.get("message")
        if not isinstance(message, dict):
            return
        message_id = message.get("id")
        if isinstance(message_id, int):
            if message_id in self.seen_message_ids:
                return
            self.seen_message_ids.add(message_id)

        sender_email = str(message.get("sender_email") or "")
        if sender_email.lower() == self.settings.zulip_email.lower():
            return
        if not self._should_handle_message(message):
            return

        logger.info("Handling Zulip message id=%s from=%s", message_id, sender_email)
        traceforge_response = self._call_traceforge(event)
        reply_text = _extract_reply_text(traceforge_response)
        self._reply_to_message(message, reply_text)
        logger.info("Replied to Zulip message id=%s", message_id)

    def _should_handle_message(self, message: dict[str, Any]) -> bool:
        message_type = str(message.get("type") or "")
        if message_type == "private":
            return True
        content = _plain_text(str(message.get("content") or ""))
        bot_name = self.settings.zulip_bot_name.lower()
        bot_email = self.settings.zulip_email.lower()
        lowered = content.lower()
        return (
            f"@{bot_name}" in lowered
            or bot_name in lowered
            or bot_email in lowered
            or f"@**{bot_name}**" in lowered
        )

    def _call_traceforge(self, event: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.settings.traceforge_api_url.rstrip('/')}/api/events/zulip"
        body = json.dumps(event).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"TraceForge API HTTP {exc.code}: {detail}") from exc

    def _reply_to_message(self, message: dict[str, Any], content: str) -> None:
        message_type = str(message.get("type") or "stream")
        if message_type == "private":
            recipients = _direct_message_recipients(message, self.settings.zulip_email)
            payload = {"type": "private", "to": json.dumps(recipients), "content": content}
        else:
            stream = _stream_name(message)
            topic = str(message.get("subject") or message.get("topic") or "")
            payload = {"type": "stream", "to": stream, "topic": topic, "content": content}
        self._zulip_post("/api/v1/messages", payload)

    def _zulip_get(
        self, path: str, params: dict[str, str], timeout_seconds: float = 30
    ) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        return self._zulip_request("GET", f"{path}?{query}", None, timeout_seconds)

    def _zulip_post(
        self, path: str, data: dict[str, str], timeout_seconds: float = 30
    ) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        return self._zulip_request("POST", path, encoded, timeout_seconds)

    def _zulip_request(
        self, method: str, path: str, body: bytes | None, timeout_seconds: float
    ) -> dict[str, Any]:
        url = f"{self.settings.zulip_url.rstrip('/')}{path}"
        request = urllib.request.Request(
            url=url,
            data=body,
            headers={
                "Authorization": f"Basic {self._basic_auth_token()}",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method=method,
        )
        context = None if self.settings.zulip_verify_ssl else ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds, context=context) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Zulip API HTTP {exc.code}: {detail}") from exc
        if payload.get("result") == "error":
            raise RuntimeError(f"Zulip API error: {payload}")
        return payload

    def _basic_auth_token(self) -> str:
        raw = f"{self.settings.zulip_email}:{self.settings.zulip_api_key}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _validate_settings(self) -> None:
        if not self.settings.zulip_api_key:
            raise ValueError("ZULIP_API_KEY is required")


def _extract_reply_text(response: dict[str, Any]) -> str:
    result = response.get("result")
    if isinstance(result, dict) and isinstance(result.get("reply_text"), str):
        return result["reply_text"]
    return "TraceForge 已收到消息，但没有生成回复内容。"


def _stream_name(message: dict[str, Any]) -> str:
    display_recipient = message.get("display_recipient")
    if isinstance(display_recipient, str) and display_recipient:
        return display_recipient
    stream_id = message.get("stream_id")
    if stream_id is None:
        raise ValueError("stream message missing display_recipient/stream_id")
    return str(stream_id)


def _direct_message_recipients(message: dict[str, Any], bot_email: str) -> list[str]:
    display_recipient = message.get("display_recipient")
    recipients: list[str] = []
    if isinstance(display_recipient, list):
        for item in display_recipient:
            if isinstance(item, dict) and isinstance(item.get("email"), str):
                email = item["email"]
                if email.lower() != bot_email.lower():
                    recipients.append(email)
    sender_email = message.get("sender_email")
    if not recipients and isinstance(sender_email, str):
        recipients.append(sender_email)
    return recipients


def _plain_text(html_or_text: str) -> str:
    text = html_or_text.replace("<p>", "").replace("</p>", " ")
    for token in ("<strong>", "</strong>", "<em>", "</em>"):
        text = text.replace(token, "")
    return text.strip()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ZulipTraceForgeBridge().run_forever()


if __name__ == "__main__":
    main()
