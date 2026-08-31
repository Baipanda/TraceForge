from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from traceforge.agent.models import ModelToolCall, ModelTurn
from traceforge.config import TraceForgeSettings
from traceforge.core.events import WorkspaceEvent


@dataclass(frozen=True)
class LLMReply:
    content: str
    model: str


class DeepSeekClient:
    """Tiny OpenAI-compatible DeepSeek client.

    DeepSeek exposes `/chat/completions` with Bearer-token auth, so the client
    is deliberately small until TraceForge needs streaming/tool-calling.
    """

    def __init__(self, settings: TraceForgeSettings, timeout_seconds: float = 30.0) -> None:
        if not settings.deepseek_api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")
        self._api_key = settings.deepseek_api_key
        self._base_url = settings.deepseek_base_url.rstrip("/")
        self._model = settings.deepseek_model
        self._timeout_seconds = timeout_seconds

    def generate_workspace_reply(self, event: WorkspaceEvent, intent: str) -> LLMReply:
        actor = event.actor.display_name or event.actor.email or "用户"
        channel = event.location.channel_name or event.location.channel_id or "未知频道"
        topic = event.location.topic or "无 Topic"
        text = str(event.payload.get("text") or "")
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 TraceForge 项目中的 Jarvis，一个面向研发/安全团队的 Workspace Agent。"
                    "当前阶段只需要完成 Zulip 中的简洁回复，不要假装已经创建数据库任务或完成真实工具调用。"
                    "你可以说明已理解请求、识别到的意图、下一步将进入哪个工具/Agent 阶段。"
                    "回复使用中文，简洁、工程化、可信，不要输出冗长解释。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"发送者：{actor}\n"
                    f"频道：{channel}\n"
                    f"Topic：{topic}\n"
                    f"识别意图：{intent}\n"
                    f"用户原文：{text}\n\n"
                    "请生成一条适合作为 Zulip bot 回帖的内容。"
                ),
            },
        ]
        return self.chat(messages)

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> ModelTurn:
        response = self._request(
            [
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            tools=tools,
        )
        message = _extract_message(response)
        return ModelTurn(
            content=str(message.get("content") or "").strip(),
            tool_calls=_extract_tool_calls(message),
        )

    def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 600) -> LLMReply:
        payload = self._request(messages, max_tokens=max_tokens)
        content = _extract_content(payload)
        return LLMReply(content=content, model=self._model)

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2000,
    ) -> str:
        payload = self._request(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.1,
        )
        return _extract_content(payload)

    def _request(
        self,
        messages: list[dict[str, object]],
        *,
        tools: list[dict[str, object]] | None = None,
        max_tokens: int = 600,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        body = {
            "model": self._model,
            "messages": messages,
            "thinking": {"type": "disabled"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("schema", {}),
                    },
                }
                for tool in tools
            ]
        request = urllib.request.Request(
            url=f"{self._base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc.reason}") from exc

        return payload


def _extract_message(payload: dict[str, Any]) -> dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("DeepSeek API response missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("DeepSeek API response missing message")
    return message


def _extract_tool_calls(message: dict[str, Any]) -> list[ModelToolCall]:
    raw_calls = message.get("tool_calls")
    if not isinstance(raw_calls, list):
        return []
    calls: list[ModelToolCall] = []
    for index, raw_call in enumerate(raw_calls):
        if not isinstance(raw_call, dict):
            continue
        function = raw_call.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        raw_arguments = function.get("arguments") or "{}"
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid tool arguments for {name}") from exc
        if not isinstance(arguments, dict):
            raise RuntimeError(f"Tool arguments for {name} must be an object")
        calls.append(
            ModelToolCall(
                call_id=str(raw_call.get("id") or f"tool_call_{index}"),
                name=name,
                arguments=arguments,
            )
        )
    return calls


def _extract_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("DeepSeek API response missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("DeepSeek API response missing message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("DeepSeek API response missing content")
    return content.strip()
