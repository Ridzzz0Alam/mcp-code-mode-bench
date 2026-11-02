"""The agent loop and system prompt shared by all conditions.

Conditions differ only in their Exposure: the prompt block, the tool list, and how a call executes.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any

from llm import LLM, ApiFailure, ContextOverflow, OversizedRequestFailure, Usage

MAX_TURNS = 25

SYSTEM_CORE = """You are an assistant that completes business requests using the tools available to you.

Today's date is 2026-03-15. Complete the request fully and do not ask the user for clarification.
If the request asks a question, end your final message with the answer inside <answer></answer> tags, containing only the answer in the requested format.
If the request asks you to change something, make the change and then reply with a short confirmation.
A reply with no tool call is treated as your final message."""


class Exposure:
    """How one condition exposes tools to the model."""

    def __init__(self) -> None:
        self.code_executions = 0
        self.sandbox_errors = 0
        self.truncated_outputs = 0

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def system_block(self) -> str:
        raise NotImplementedError

    def tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        raise NotImplementedError


def system_prompt(exposure: Exposure) -> str:
    return f"{SYSTEM_CORE}\n\n## How tools are exposed\n{exposure.system_block()}"


@dataclass
class RunOutcome:
    final_message: str = ""
    stop_reason: str = "final"
    error: str | None = None
    error_detail: str | None = None
    model_turns: int = 0
    cache_hits: int = 0
    wall_time_s: float = 0.0
    usages: list[Usage] = field(default_factory=list)


def _total(usages: list[Usage], name: str) -> int | None:
    """Sum one usage field. Token counts are never estimated, so any gap makes the total unknown."""
    values = [getattr(usage, name) for usage in usages]
    return None if not values or any(value is None for value in values) else sum(values)


def usage_totals(usages: list[Usage]) -> dict[str, int | None]:
    return {name: _total(usages, name) for name in ["input_tokens", "output_tokens", "total_tokens", "cached_input_tokens"]}


async def run_agent(llm: LLM, model: str, trial: int | str, exposure: Exposure, prompt: str, session_id: str | None = None) -> RunOutcome:
    outcome = RunOutcome()
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(exposure)}, {"role": "user", "content": prompt}]
    while outcome.model_turns < MAX_TURNS:
        try:
            response = await llm.complete(model, trial, messages, exposure.tools(), session_id)
        except ContextOverflow as failure:
            outcome.stop_reason = outcome.error = "context_overflow"
            outcome.error_detail = str(failure)
            return outcome
        except OversizedRequestFailure as failure:
            outcome.stop_reason = outcome.error = "oversized_request"
            outcome.error_detail = str(failure)
            return outcome
        except ApiFailure as failure:
            outcome.stop_reason = outcome.error = "api_error"
            outcome.error_detail = str(failure)
            return outcome
        outcome.model_turns += 1
        outcome.cache_hits += response.cache_hit
        outcome.wall_time_s += response.latency_s
        outcome.usages.append(response.usage)
        messages.append(response.message)
        calls = response.message.get("tool_calls")
        if not calls:
            outcome.final_message = response.message["content"]
            return outcome
        started = time.perf_counter()
        for call in calls:
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": await _execute(exposure, call)})
        outcome.wall_time_s += time.perf_counter() - started
    outcome.stop_reason = outcome.error = "max_turns"
    return outcome


async def _execute(exposure: Exposure, call: dict[str, Any]) -> str:
    try:
        arguments = json.loads(call["function"]["arguments"] or "{}")
    except json.JSONDecodeError as error:
        return f"Error: tool arguments were not valid JSON: {error}"
    if not isinstance(arguments, dict):
        return "Error: tool arguments must be a JSON object"
    return await exposure.execute(call["function"]["name"], arguments)
