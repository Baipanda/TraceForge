"""Zulip REST client for Topic history (API-only, no direct DB access)."""

from __future__ import annotations

import base64
import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from traceforge.config import TraceForgeSettings, get_settings
from traceforge.interfaces.zulip.normalizer import strip_zulip_markup

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ZulipTopicMessage:
    id: int
    sender_name: str
    sender_email: str
    content: str
    timestamp: datetime


class ZulipApiClient:
    def __init__(self, settings: TraceForgeSettings | None = None) -> None:
        self.settings = settings or get_settings()

    def send_stream_message(
        self,
        *,
        stream: str,
        topic: str,
        content: str,
        email: str | None = None,
        api_key: str | None = None,
    ) -> int | None:
        """Post a stream message; returns Zulip message id when present."""
        payload = {
            "type": "stream",
            "to": stream,
            "topic": topic,
            "content": content,
        }
        body = urllib.parse.urlencode(payload).encode("utf-8")
        result = self._request(
            "POST",
            "/api/v1/messages",
            body,
            30,
            email=email,
            api_key=api_key,
        )
        mid = result.get("id")
        return int(mid) if isinstance(mid, int) else None

    def ensure_stream_subscription(
        self,
        *,
        stream: str,
        email: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Best-effort subscribe the auth identity to a stream (bots need this to post)."""
        subscriptions = json.dumps([{"name": stream}])
        body = urllib.parse.urlencode({"subscriptions": subscriptions}).encode("utf-8")
        try:
            self._request(
                "POST",
                "/api/v1/users/me/subscriptions",
                body,
                30,
                email=email,
                api_key=api_key,
            )
        except RuntimeError as exc:
            # Already subscribed / stream missing — caller will see send errors if fatal.
            if "already" in str(exc).lower():
                return
            logger.warning("ensure_stream_subscription: %s", exc)

    def fetch_topic_messages_all(
        self,
        *,
        stream: str,
        topic: str,
        page_size: int = 500,
        exclude_sender_email: str | None = None,
    ) -> list[ZulipTopicMessage]:
        """Fetch all messages in a stream Topic via paginated GET /messages."""
        if not self.settings.zulip_api_key:
            raise RuntimeError("ZULIP_API_KEY is not configured")
        stream = (stream or "").strip()
        topic = (topic or "").strip()
        if not stream or not topic:
            raise ValueError("stream and topic are required")

        exclude = (exclude_sender_email or self.settings.zulip_email or "").strip().lower()
        narrow = json.dumps([["stream", stream], ["topic", topic]])
        collected: dict[int, ZulipTopicMessage] = {}
        anchor: str | int = "newest"
        page_size = max(1, min(page_size, 5000))

        while True:
            payload = self._get(
                "/api/v1/messages",
                {
                    "anchor": str(anchor),
                    "num_before": str(page_size),
                    "num_after": "0",
                    "narrow": narrow,
                    "apply_markdown": "false",
                },
            )
            batch = payload.get("messages") or []
            if not batch:
                break
            oldest_id: int | None = None
            for item in batch:
                if not isinstance(item, dict):
                    continue
                parsed = self._parse_message(item, exclude_email=exclude)
                if parsed is None:
                    continue
                collected[parsed.id] = parsed
                if oldest_id is None or parsed.id < oldest_id:
                    oldest_id = parsed.id
            if oldest_id is None:
                break
            if len(batch) < page_size:
                break
            # Next page: messages strictly before the oldest id in this batch.
            if anchor == oldest_id:
                break
            anchor = oldest_id

        return [collected[mid] for mid in sorted(collected)]

    def _parse_message(
        self, item: dict[str, Any], *, exclude_email: str
    ) -> ZulipTopicMessage | None:
        mid = item.get("id")
        if not isinstance(mid, int):
            return None
        sender_email = str(item.get("sender_email") or "").strip()
        if exclude_email and sender_email.lower() == exclude_email:
            return None
        content = strip_zulip_markup(str(item.get("content") or ""))
        if not content:
            return None
        ts = item.get("timestamp")
        try:
            when = datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            when = datetime.now(timezone.utc)
        return ZulipTopicMessage(
            id=mid,
            sender_name=str(item.get("sender_full_name") or sender_email or "unknown"),
            sender_email=sender_email,
            content=content,
            timestamp=when,
        )

    def _get(self, path: str, params: dict[str, str], timeout_seconds: float = 60) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        return self._request("GET", f"{path}?{query}", None, timeout_seconds)

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None,
        timeout_seconds: float,
        *,
        email: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        logical_base = self.settings.zulip_url.rstrip("/")
        connect_base = (self.settings.zulip_api_connect_url or logical_base).rstrip("/")
        url = f"{connect_base}{path}"
        headers = {
            "Authorization": f"Basic {self._basic_auth_token(email=email, api_key=api_key)}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        logical_host = urllib.parse.urlparse(logical_base).netloc
        connect_host = urllib.parse.urlparse(connect_base).netloc
        if logical_host and logical_host != connect_host:
            headers["Host"] = logical_host
        request = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
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

    def _basic_auth_token(self, *, email: str | None = None, api_key: str | None = None) -> str:
        use_email = (email or self.settings.zulip_email or "").strip()
        use_key = (api_key or self.settings.zulip_api_key or "").strip()
        if not use_key:
            raise RuntimeError("ZULIP_API_KEY is not configured")
        raw = f"{use_email}:{use_key}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")
