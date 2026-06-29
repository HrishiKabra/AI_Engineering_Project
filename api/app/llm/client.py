"""Chat LLM wrapper around the OpenAI SDK.

Returns text + token usage so the agent can accumulate cost. Supports JSON-mode
for the router/grader nodes and a streaming generator for the answer.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any, Protocol

from openai import OpenAI


class ChatLLM(Protocol):
    model: str

    def chat(self, system: str, user: str, **kw: Any) -> dict: ...
    def chat_json(self, system: str, user: str, **kw: Any) -> dict: ...
    def stream(self, system: str, user: str, **kw: Any) -> Iterator[str]: ...


class OpenAIChat:
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.1, max_tokens: int = 700):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = OpenAI()

    def _messages(self, system: str, user: str) -> list[dict]:
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def chat(self, system: str, user: str, *, temperature: float | None = None,
             max_tokens: int | None = None, json_mode: bool = False) -> dict:
        kw: dict[str, Any] = {
            "model": self.model,
            "messages": self._messages(system, user),
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if json_mode:
            kw["response_format"] = {"type": "json_object"}
        resp = self._client.chat.completions.create(**kw)
        return {
            "text": resp.choices[0].message.content or "",
            "prompt_tokens": resp.usage.prompt_tokens,
            "completion_tokens": resp.usage.completion_tokens,
            "model": self.model,
        }

    def chat_json(self, system: str, user: str, **kw: Any) -> dict:
        out = self.chat(system, user, json_mode=True, **kw)
        try:
            out["data"] = json.loads(out["text"])
        except (json.JSONDecodeError, TypeError):
            out["data"] = {}
        return out

    def stream(self, system: str, user: str, *, temperature: float | None = None,
               max_tokens: int | None = None) -> Iterator[str]:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=self._messages(system, user),
            temperature=self.temperature if temperature is None else temperature,
            max_tokens=max_tokens or self.max_tokens,
            stream=True,
        )
        for chunk in resp:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
