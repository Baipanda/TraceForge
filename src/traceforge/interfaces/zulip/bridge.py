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


@dataclass(frozen=True)
class ZulipBotAccount:
    """One Zulip delivery/listen identity for the bridge."""

    email: str
    api_key: str
    bot_name: str
    agent_id: str = "main"


@dataclass
class ZulipTraceForgeBridge:
    settings: TraceForgeSettings = field(default_factory=get_settings)
    account: ZulipBotAccount | None = None
    seen_message_ids: set[int] = field(default_factory=set)

    def _bot(self) -> ZulipBotAccount:
        if self.account is not None:
            return self.account
        return ZulipBotAccount(
            email=self.settings.zulip_email,
            api_key=self.settings.zulip_api_key,
            bot_name=self.settings.zulip_bot_name or "Jarvis",
            agent_id="main",
        )

    def run_forever(self) -> None:
        self._validate_settings()
        bot = self._bot()
        queue = self._register_queue()
        queue_id = queue["queue_id"]
        last_event_id = int(queue["last_event_id"])
        logger.info(
            "Zulip bridge registered bot=%s agent_id=%s queue_id=%s last_event_id=%s",
            bot.bot_name,
            bot.agent_id,
            queue_id,
            last_event_id,
        )

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
            except Exception as exc:
                if _is_bad_event_queue(exc):
                    logger.warning("Zulip event queue expired; registering a new queue")
                    queue = self._register_queue()
                    queue_id = queue["queue_id"]
                    last_event_id = int(queue["last_event_id"])
                    logger.info(
                        "Zulip bridge re-registered queue_id=%s last_event_id=%s",
                        queue_id,
                        last_event_id,
                    )
                    continue
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
        bot = self._bot()
        if sender_email.lower() == bot.email.lower():
            return
        if not self._should_handle_message(message):
            return

        logger.info(
            "Handling Zulip message id=%s from=%s bot=%s agent_id=%s",
            message_id,
            sender_email,
            bot.bot_name,
            bot.agent_id,
        )
        self._start_progress(message)
        succeeded = False
        try:
            traceforge_response = self._call_traceforge(event)
            reply_text = _extract_reply_text(traceforge_response)
            self._reply_to_message(message, reply_text)
            succeeded = True
            logger.info("Replied to Zulip message id=%s", message_id)
        except Exception as exc:
            logger.exception("TraceForge request failed for Zulip message id=%s", message_id)
            try:
                self._reply_to_message(
                    message,
                    "TraceForge 处理这条请求时遇到错误，动作没有被确认完成。"
                    f"\n错误类型：{type(exc).__name__}",
                )
            except Exception:
                logger.exception("Failed to send TraceForge error reply for message id=%s", message_id)
        finally:
            self._stop_progress(message, succeeded=succeeded)

    def _should_handle_message(self, message: dict[str, Any]) -> bool:
        message_type = str(message.get("type") or "")
        if message_type == "private":
            return True
        content = _plain_text(str(message.get("content") or ""))
        bot = self._bot()
        bot_name = bot.bot_name.lower()
        bot_email = bot.email.lower()
        lowered = content.lower()
        return (
            f"@{bot_name}" in lowered
            or bot_name in lowered
            or bot_email in lowered
            or f"@**{bot_name}**" in lowered
        )

    def _call_traceforge(self, event: dict[str, Any]) -> dict[str, Any]:
        bot = self._bot()
        enriched = dict(event) if isinstance(event, dict) else {"raw_event": event}
        enriched["traceforge_delivery"] = {
            "account": bot.email,
            "email": bot.email,
            "bot_email": bot.email,
            "bot_name": bot.bot_name,
            "agent_id": bot.agent_id,
        }
        url = f"{self.settings.traceforge_api_url.rstrip('/')}/api/events/zulip"
        body = json.dumps(enriched).encode("utf-8")
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
        bot = self._bot()
        message_type = str(message.get("type") or "stream")
        if message_type == "private":
            recipients = _direct_message_recipients(message, bot.email)
            payload = {"type": "private", "to": json.dumps(recipients), "content": content}
        else:
            stream = _stream_name(message)
            topic = str(message.get("subject") or message.get("topic") or "")
            payload = {"type": "stream", "to": stream, "topic": topic, "content": content}
        self._zulip_post("/api/v1/messages", payload)

    def _start_progress(self, message: dict[str, Any]) -> None:
        if self.settings.zulip_reactions_enabled:
            self._safe_reaction(message, "eyes", add=True)
        if self.settings.zulip_progress_enabled:
            self._safe_typing(message, op="start")

    def _stop_progress(self, message: dict[str, Any], *, succeeded: bool) -> None:
        if self.settings.zulip_progress_enabled:
            self._safe_typing(message, op="stop")
        if self.settings.zulip_reactions_enabled:
            self._safe_reaction(message, "eyes", add=False)
            self._safe_reaction(message, "check_mark" if succeeded else "warning", add=True)

    def _safe_typing(self, message: dict[str, Any], *, op: str) -> None:
        payload = _typing_payload(message, op=op)
        if payload is None:
            return
        try:
            self._zulip_post("/api/v1/typing", payload)
        except Exception as exc:
            logger.warning("Unable to update Zulip typing state: %s", type(exc).__name__)

    def _safe_reaction(self, message: dict[str, Any], emoji_name: str, *, add: bool) -> None:
        message_id = message.get("id")
        if message_id is None:
            return
        path = f"/api/v1/messages/{urllib.parse.quote(str(message_id), safe='')}/reactions"
        try:
            if add:
                self._zulip_post(path, {"emoji_name": emoji_name})
            else:
                self._zulip_request(
                    "DELETE",
                    f"{path}?{urllib.parse.urlencode({'emoji_name': emoji_name})}",
                    None,
                    timeout_seconds=30,
                )
        except Exception as exc:
            logger.warning(
                "Unable to update Zulip reaction message_id=%s emoji=%s: %s",
                message_id,
                emoji_name,
                type(exc).__name__,
            )

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
        bot = self._bot()
        raw = f"{bot.email}:{bot.api_key}".encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _validate_settings(self) -> None:
        bot = self._bot()
        if not bot.api_key:
            raise ValueError(f"API key required for Zulip bot {bot.bot_name}")


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


def _typing_payload(message: dict[str, Any], *, op: str) -> dict[str, str] | None:
    message_type = str(message.get("type") or "")
    if message_type == "private":
        user_ids: list[int] = []
        display_recipient = message.get("display_recipient")
        if isinstance(display_recipient, list):
            for item in display_recipient:
                if isinstance(item, dict) and item.get("id") is not None:
                    try:
                        user_ids.append(int(item["id"]))
                    except (TypeError, ValueError):
                        continue
        if not user_ids and message.get("sender_id") is not None:
            try:
                user_ids.append(int(message["sender_id"]))
            except (TypeError, ValueError):
                return None
        if not user_ids:
            return None
        return {
            "op": op,
            "type": "direct",
            "to": json.dumps(user_ids),
        }

    stream_id = message.get("stream_id")
    topic = str(message.get("subject") or message.get("topic") or "")
    if stream_id is None or not topic:
        return None
    return {
        "op": op,
        "type": "stream",
        "stream_id": str(stream_id),
        "topic": topic,
    }


def _plain_text(html_or_text: str) -> str:
    text = html_or_text.replace("<p>", "").replace("</p>", " ")
    for token in ("<strong>", "</strong>", "<em>", "</em>"):
        text = text.replace(token, "")
    return text.strip()


def _is_bad_event_queue(exc: Exception) -> bool:
    text = str(exc)
    return "BAD_EVENT_QUEUE_ID" in text or "Bad event queue ID" in text


def main() -> None:
    import threading

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    accounts: list[ZulipBotAccount] = [
        ZulipBotAccount(
            email=settings.zulip_email,
            api_key=settings.zulip_api_key,
            bot_name=settings.zulip_bot_name or "Jarvis",
            agent_id="main",
        )
    ]
    repo_email = (settings.repoaudit_zulip_email or "").strip()
    repo_key = (settings.repoaudit_zulip_api_key or "").strip()
    if repo_email and repo_key:
        accounts.append(
            ZulipBotAccount(
                email=repo_email,
                api_key=repo_key,
                bot_name="RepoAudit",
                agent_id="gitea-audit",
            )
        )
    else:
        logger.warning("RepoAudit Zulip credentials missing; only Jarvis bridge will run")

    if len(accounts) == 1:
        ZulipTraceForgeBridge(settings=settings, account=accounts[0]).run_forever()
        return

    threads: list[threading.Thread] = []
    for account in accounts:
        bridge = ZulipTraceForgeBridge(settings=settings, account=account)
        thread = threading.Thread(
            target=bridge.run_forever,
            name=f"zulip-bridge-{account.bot_name}",
            daemon=True,
        )
        threads.append(thread)
        thread.start()
        logger.info("Started Zulip bridge thread for %s → agent %s", account.bot_name, account.agent_id)
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
