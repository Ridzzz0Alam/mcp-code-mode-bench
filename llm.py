"""Model client with on-disk cache, retries and a hard request cap."""

import asyncio
import hashlib
import json
import os
import random
import re
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openai

MAX_RETRIES = 4
BACKOFF_BASE_S = 2.0
BACKOFF_CAP_S = 60.0
REQUEST_TIMEOUT_S = 300.0
# Far above any normal turn, so a timeout or 5xx at this size is not treated as transient.
OVERSIZED_REQUEST_CHARS = 500_000
_OVERFLOW = re.compile(r"context|too long|too large|token limit|maximum.*(token|length)|exceed", re.IGNORECASE)


class RequestCapReached(Exception):
    """--max-requests was reached. The unfinished run must not be logged."""


class ContextOverflow(Exception):
    """The API rejected the request because the context is too large. Not retried."""


class OversizedRequestFailure(Exception):
    """An oversized request timed out or hit a server error. Not retried, because it would repeat."""


class ApiFailure(Exception):
    """The API failed after retries, or with a non-retryable error."""


@dataclass
class Usage:
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    cached_input_tokens: int | None


@dataclass
class LLMResponse:
    message: dict[str, Any]
    usage: Usage
    latency_s: float
    cache_hit: bool


def _message_dict(message: Any) -> dict[str, Any]:
    """Keep what must be sent back on the next turn, including provider reasoning fields."""
    result: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        result["tool_calls"] = [
            {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}}
            for call in message.tool_calls
        ]
    reasoning = (message.model_extra or {}).get("reasoning_content")
    if reasoning:
        result["reasoning_content"] = reasoning
    return result


def _usage_dict(usage: Any) -> dict[str, int | None]:
    if usage is None:
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None, "cached_input_tokens": None}
    details = usage.prompt_tokens_details
    return {
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "cached_input_tokens": details.cached_tokens if details else None,
    }


class LLM:
    def __init__(
        self,
        client: Any,
        cache_dir: Path,
        max_requests: int | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.client = client
        self.cache_dir = cache_dir
        self.max_requests = max_requests
        self.requests_sent = 0
        self.temperature_dropped: set[str] = set()
        self._sleep = sleep
        self._rng = rng or random.Random()
        cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def cache_key(model: str, trial: int | str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
        # Temperature is always requested as 0, so dropping it for a model does not change the key.
        canonical = json.dumps({"model": model, "trial": trial, "messages": messages, "tools": tools, "temperature": 0}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def complete(self, model: str, trial: int | str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], session_id: str | None = None) -> LLMResponse:
        path = self.cache_dir / f"{self.cache_key(model, trial, messages, tools)}.json"
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))
            return LLMResponse(stored["message"], Usage(**stored["usage"]), stored["latency_s"], True)
        response, latency = await self._send(model, messages, tools, session_id)
        stored = {
            "message": _message_dict(response.choices[0].message),
            "usage": _usage_dict(response.usage),
            "latency_s": latency,
            "provider_extra": response.model_extra if hasattr(response, "model_extra") else None,
        }
        self._write_atomic(path, stored)
        return LLMResponse(stored["message"], Usage(**stored["usage"]), latency, False)

    async def _send(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], session_id: str | None) -> tuple[Any, float]:
        retries = 0
        oversized = len(json.dumps(messages)) + len(json.dumps(tools)) > OVERSIZED_REQUEST_CHARS
        while True:
            if self.max_requests is not None and self.requests_sent >= self.max_requests:
                raise RequestCapReached
            self.requests_sent += 1
            kwargs: dict[str, Any] = {"model": model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
            if session_id:
                kwargs["extra_headers"] = {"x-opencode-session": session_id}
            if model not in self.temperature_dropped:
                kwargs["temperature"] = 0
            started = time.perf_counter()
            try:
                response = await self.client.chat.completions.create(**kwargs)
            except openai.APIStatusError as error:
                status = error.status_code
                if status in (400, 422) and "temperature" in str(error).lower() and model not in self.temperature_dropped:
                    self.temperature_dropped.add(model)
                    continue
                if status == 413 or (status in (400, 422) and _OVERFLOW.search(str(error))):
                    raise ContextOverflow(str(error)) from error
                if status != 429 and status < 500:
                    raise ApiFailure(f"HTTP {status}: {error}") from error
                failure = f"HTTP {status}: {error}"
                if status >= 500 and oversized:
                    raise OversizedRequestFailure(failure) from error
            except openai.APIConnectionError as error:
                failure = f"{type(error).__name__}: {error}"
                if oversized:
                    raise OversizedRequestFailure(failure) from error
            else:
                if response.choices:
                    return response, time.perf_counter() - started
                failure = "Response had no choices"
            if retries >= MAX_RETRIES:
                raise ApiFailure(failure)
            await self._sleep(self.backoff_delay(retries))
            retries += 1

    def backoff_delay(self, retry: int) -> float:
        """Capped exponential backoff with full jitter."""
        return self._rng.uniform(0, min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**retry))

    def _write_atomic(self, path: Path, stored: dict[str, Any]) -> None:
        with tempfile.NamedTemporaryFile("w", dir=self.cache_dir, suffix=".tmp", delete=False, encoding="utf-8") as handle:
            json.dump(stored, handle, sort_keys=True)
        os.replace(handle.name, path)
