from __future__ import annotations

import json
import http.client
import urllib.error
import urllib.request
from typing import Any

from .config import ProviderSettings


class LLMAPIError(RuntimeError):
    """Raised when an OpenAI-compatible model call fails."""


class OpenAICompatibleClient:
    def __init__(self, provider: ProviderSettings, timeout_seconds: int):
        self.provider = provider
        self.timeout_seconds = timeout_seconds

    def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.provider.api_key:
            raise LLMAPIError(f"{self.provider.name} 缺少 API Key，请在 .env 中配置 {self.provider.api_key_hint}。")

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.provider.base_url}/chat/completions",
            data=body,
            method="POST",
            headers=self._headers(),
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMAPIError(f"{self.provider.name} HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMAPIError(f"无法连接 {self.provider.name}: {exc.reason}") from exc
        except (http.client.RemoteDisconnected, TimeoutError, OSError) as exc:
            raise LLMAPIError(f"{self.provider.name} 连接中断: {exc}") from exc

        if payload.get("stream"):
            return self._stream_response_to_chat_response(raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMAPIError(f"{self.provider.name} 返回了非 JSON 内容: {raw[:500]}") from exc

    def _stream_response_to_chat_response(self, raw: str) -> dict[str, Any]:
        stripped = raw.lstrip()
        if stripped.startswith("{"):
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LLMAPIError(f"{self.provider.name} 流式返回无法解析为 JSON: {raw[:500]}") from exc

        content_parts: list[str] = []
        role = "assistant"
        response_id: str | None = None
        model: str | None = None
        finish_reason: str | None = None
        usage: dict[str, Any] | None = None

        for data in self._iter_sse_data(raw):
            if data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError as exc:
                raise LLMAPIError(f"{self.provider.name} 流式片段无法解析: {data[:500]}") from exc
            if not isinstance(event, dict):
                continue

            error = event.get("error")
            if error:
                raise LLMAPIError(f"{self.provider.name} 流式返回错误: {error}")

            response_id = response_id or event.get("id")
            model = model or event.get("model")
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]

            choices = event.get("choices")
            if not isinstance(choices, list):
                continue
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                finish_reason = choice.get("finish_reason") or finish_reason

                delta = choice.get("delta")
                if isinstance(delta, dict):
                    role = delta.get("role") or role
                    text = _content_value_to_text(delta.get("content"))
                    if text:
                        content_parts.append(text)

                message = choice.get("message")
                if isinstance(message, dict):
                    role = message.get("role") or role
                    text = _content_value_to_text(message.get("content"))
                    if text:
                        content_parts.append(text)

        return {
            "id": response_id,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": {
                        "role": role,
                        "content": "".join(content_parts).strip(),
                    },
                }
            ],
            "usage": usage,
        }

    def _iter_sse_data(self, raw: str) -> list[str]:
        events: list[str] = []
        current: list[str] = []
        for raw_line in raw.splitlines():
            line = raw_line.strip()
            if not line:
                if current:
                    events.append("\n".join(current))
                    current = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                current.append(line.removeprefix("data:").lstrip())
        if current:
            events.append("\n".join(current))
        return events

    def _headers(self) -> dict[str, str]:
        header = self.provider.auth_header.strip() or "Authorization"
        scheme = self.provider.auth_scheme.strip()
        if header.lower() == "api-key":
            token = self.provider.api_key
        elif scheme:
            token = f"{scheme} {self.provider.api_key}"
        else:
            token = self.provider.api_key
        return {
            "Content-Type": "application/json",
            header: token,
        }


def _content_value_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _content_value_to_text(content.get("text") or content.get("content"))
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = _content_value_to_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    return ""


def first_message(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMAPIError(f"模型响应缺少 choices: {response}")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise LLMAPIError(f"模型响应缺少 message: {response}")
    return message


def message_text(response: dict[str, Any]) -> str:
    message = first_message(response)
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(parts).strip()
    return ""
