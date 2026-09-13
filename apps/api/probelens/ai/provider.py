"""Thin provider boundary around an OpenAI-compatible chat API.

The agent only depends on `ChatProvider`, so swapping vendors (or stubbing in
tests) is a one-class change. Nothing here knows about analytics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from probelens.config import get_settings

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass
class ChatTurn:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw_message: dict[str, Any] = field(default_factory=dict)  # appended verbatim to history

class ChatProvider(Protocol):
    model: str

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        json_response: bool = False,
        temperature: float = 0.1,
    ) -> ChatTurn: ...

class OpenAICompatibleProvider:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 60.0) -> None:
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=1)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        json_response: bool = False,
        temperature: float = 0.1,
    ) -> ChatTurn:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if json_response:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            calls.append(
                ToolCall(id=tc.id, name=tc.function.name, arguments=args if isinstance(args, dict) else {})
            )
        usage = resp.usage
        return ChatTurn(
            content=msg.content,
            tool_calls=calls,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            raw_message=msg.model_dump(exclude_none=True),
        )

def get_provider() -> ChatProvider | None:
    """None means demo mode: no key configured, so the deterministic analyst runs."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    return OpenAICompatibleProvider(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
