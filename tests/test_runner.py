"""Client, loop and runner tests. These use a fake API client and never touch the network."""

import argparse
import json
import random
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest

import runner
from agents.common import MAX_TURNS, SYSTEM_CORE, Exposure, run_agent, usage_totals
from llm import BACKOFF_CAP_S, LLM, MAX_RETRIES, OVERSIZED_REQUEST_CHARS, ApiFailure, ContextOverflow, OversizedRequestFailure, RequestCapReached

Script = Callable[[dict[str, Any]], Any]


def status_error(status: int, message: str = "boom") -> openai.APIStatusError:
    response = httpx2.Response(status, request=httpx2.Request("POST", "http://fake/chat"))
    return openai.APIStatusError(message, response=response, body=None)


def reply(content: str = "", calls: list[tuple[str, str]] | None = None, usage: bool = True, reasoning: str | None = None) -> SimpleNamespace:
    tool_calls = [SimpleNamespace(id=f"call_{i}", function=SimpleNamespace(name=name, arguments=args)) for i, (name, args) in enumerate(calls or [])]
    message = SimpleNamespace(content=content, tool_calls=tool_calls or None, model_extra={"reasoning_content": reasoning} if reasoning else {})
    counts = SimpleNamespace(prompt_tokens=100, completion_tokens=10, total_tokens=110, prompt_tokens_details=SimpleNamespace(cached_tokens=40)) if usage else None
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=counts)


class FakeClient:
    def __init__(self, script: Script) -> None:
        self.script = script
        self.requests: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        self.requests.append(json.loads(json.dumps(kwargs)))
        result = self.script(kwargs)
        if isinstance(result, Exception):
            raise result
        return result


def make_llm(client: FakeClient, tmp_path: Path, max_requests: int | None = None) -> tuple[LLM, list[float]]:
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return LLM(client, tmp_path / "cache", max_requests, sleep=sleep, rng=random.Random(1)), sleeps


MESSAGES = [{"role": "user", "content": "hi"}]


async def test_cache_hit_replays_usage_and_latency(tmp_path: Path) -> None:
    client = FakeClient(lambda _: reply("hello"))
    llm, _ = make_llm(client, tmp_path)
    first = await llm.complete("m", 1, MESSAGES, [])
    second = await llm.complete("m", 1, MESSAGES, [])
    assert len(client.requests) == 1 and llm.requests_sent == 1
    assert not first.cache_hit and second.cache_hit
    assert second.usage == first.usage and second.latency_s == first.latency_s
    assert second.usage.cached_input_tokens == 40


@pytest.mark.parametrize("change", [{"trial": 2}, {"model": "other"}, {"messages": [{"role": "user", "content": "x"}]}, {"tools": [{"type": "function"}]}])
async def test_cache_misses_when_any_key_part_differs(tmp_path: Path, change: dict[str, Any]) -> None:
    client = FakeClient(lambda _: reply("hello"))
    llm, _ = make_llm(client, tmp_path)
    base = {"model": "m", "trial": 1, "messages": MESSAGES, "tools": []}
    await llm.complete(**base)
    await llm.complete(**{**base, **change})
    assert len(client.requests) == 2


async def test_retries_then_succeeds(tmp_path: Path) -> None:
    results = [status_error(429), status_error(503), reply("ok")]
    client = FakeClient(lambda _: results.pop(0))
    llm, sleeps = make_llm(client, tmp_path)
    assert (await llm.complete("m", 1, MESSAGES, [])).message["content"] == "ok"
    assert len(sleeps) == 2 and llm.requests_sent == 3


async def test_retry_limit_gives_up_and_nothing_is_cached(tmp_path: Path) -> None:
    client = FakeClient(lambda _: status_error(500))
    llm, sleeps = make_llm(client, tmp_path)
    with pytest.raises(ApiFailure):
        await llm.complete("m", 1, MESSAGES, [])
    assert len(client.requests) == MAX_RETRIES + 1 and len(sleeps) == MAX_RETRIES
    assert not list((tmp_path / "cache").iterdir())


async def test_connection_errors_are_retried(tmp_path: Path) -> None:
    results = [openai.APIConnectionError(request=httpx2.Request("POST", "http://fake")), reply("ok")]
    llm, sleeps = make_llm(FakeClient(lambda _: results.pop(0)), tmp_path)
    assert (await llm.complete("m", 1, MESSAGES, [])).message["content"] == "ok"
    assert len(sleeps) == 1


async def test_auth_errors_are_not_retried(tmp_path: Path) -> None:
    client = FakeClient(lambda _: status_error(401))
    llm, _ = make_llm(client, tmp_path)
    with pytest.raises(ApiFailure):
        await llm.complete("m", 1, MESSAGES, [])
    assert len(client.requests) == 1


def test_backoff_has_full_jitter_and_a_cap(tmp_path: Path) -> None:
    llm, _ = make_llm(FakeClient(lambda _: reply()), tmp_path)
    delays = [llm.backoff_delay(30) for _ in range(200)]
    assert all(0 <= d <= BACKOFF_CAP_S for d in delays)
    assert max(delays) > BACKOFF_CAP_S / 2 and min(delays) < BACKOFF_CAP_S / 2


@pytest.mark.parametrize("error", [status_error(413), status_error(400, "maximum context length exceeded")])
async def test_context_overflow_is_not_retried(tmp_path: Path, error: Exception) -> None:
    client = FakeClient(lambda _: error)
    llm, _ = make_llm(client, tmp_path)
    with pytest.raises(ContextOverflow):
        await llm.complete("m", 1, MESSAGES, [])
    assert len(client.requests) == 1


async def test_temperature_is_dropped_if_rejected(tmp_path: Path) -> None:
    def script(kwargs: dict[str, Any]) -> Any:
        return status_error(400, "temperature is not supported") if "temperature" in kwargs else reply("ok")

    client = FakeClient(script)
    llm, _ = make_llm(client, tmp_path)
    await llm.complete("m", 1, MESSAGES, [])
    await llm.complete("m", 2, MESSAGES, [])
    assert llm.temperature_dropped == {"m"}
    assert [("temperature" in r) for r in client.requests] == [True, False, False]


async def test_request_cap_counts_retries_but_not_cache_hits(tmp_path: Path) -> None:
    client = FakeClient(lambda _: reply("ok"))
    llm, _ = make_llm(client, tmp_path, max_requests=1)
    await llm.complete("m", 1, MESSAGES, [])
    await llm.complete("m", 1, MESSAGES, [])
    with pytest.raises(RequestCapReached):
        await llm.complete("m", 2, MESSAGES, [])
    assert len(client.requests) == 1

    failing = FakeClient(lambda _: status_error(500))
    llm, _ = make_llm(failing, tmp_path / "two", max_requests=2)
    with pytest.raises(RequestCapReached):
        await llm.complete("m", 1, MESSAGES, [])
    assert len(failing.requests) == 2


class EchoExposure(Exposure):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[tuple[str, dict[str, Any]]] = []

    def system_block(self) -> str:
        return "BLOCK"

    def tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": "echo", "parameters": {"type": "object"}}}]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        self.seen.append((name, arguments))
        return f"ran {name}"


async def test_loop_runs_parallel_calls_and_returns_final_message(tmp_path: Path) -> None:
    results = [reply(calls=[("echo", '{"a":1}'), ("echo", '{"a":2}')], reasoning="thinking"), reply("<answer>7</answer>")]
    client = FakeClient(lambda _: results.pop(0))
    llm, _ = make_llm(client, tmp_path)
    exposure = EchoExposure()
    outcome = await run_agent(llm, "m", 1, exposure, "task")
    assert outcome.final_message == "<answer>7</answer>" and outcome.error is None and outcome.model_turns == 2
    assert [args for _, args in exposure.seen] == [{"a": 1}, {"a": 2}]
    second = client.requests[1]["messages"]
    assert second[0]["content"].startswith(SYSTEM_CORE) and second[0]["content"].endswith("BLOCK")
    assert second[2]["reasoning_content"] == "thinking"
    assert [(m["role"], m.get("tool_call_id")) for m in second[3:]] == [("tool", "call_0"), ("tool", "call_1")]
    assert usage_totals(outcome.usages) == {"input_tokens": 200, "output_tokens": 20, "total_tokens": 220, "cached_input_tokens": 80}


async def test_malformed_arguments_go_back_to_the_model(tmp_path: Path) -> None:
    results = [reply(calls=[("echo", "{bad")]), reply("done")]
    client = FakeClient(lambda _: results.pop(0))
    llm, _ = make_llm(client, tmp_path)
    exposure = EchoExposure()
    outcome = await run_agent(llm, "m", 1, exposure, "task")
    assert outcome.final_message == "done" and exposure.seen == []
    assert "not valid JSON" in client.requests[1]["messages"][-1]["content"]


async def test_loop_stops_at_max_turns(tmp_path: Path) -> None:
    counter = iter(range(100))
    client = FakeClient(lambda _: reply(calls=[("echo", json.dumps({"n": next(counter)}))]))
    llm, _ = make_llm(client, tmp_path)
    outcome = await run_agent(llm, "m", 1, EchoExposure(), "task")
    assert outcome.error == outcome.stop_reason == "max_turns"
    assert outcome.model_turns == MAX_TURNS == len(client.requests)


async def test_missing_usage_stays_unknown(tmp_path: Path) -> None:
    llm, _ = make_llm(FakeClient(lambda _: reply("x", usage=False)), tmp_path)
    outcome = await run_agent(llm, "m", 1, EchoExposure(), "task")
    assert usage_totals(outcome.usages)["total_tokens"] is None


def args_for(**overrides: Any) -> argparse.Namespace:
    values = {"models": "m1", "conditions": "A", "tasks": "S05", "trials": 1, "dry_run": False, "max_requests": None, "retry_errors": False, "list_models": False, "approved": True}
    return argparse.Namespace(**{**values, **overrides})


def answer_from_tools(kwargs: dict[str, Any]) -> Any:
    """Plays a model that reads contact C-0123 and reports its email."""
    last = kwargs["messages"][-1]
    if last["role"] == "user":
        return reply(calls=[("get_contact", '{"contact_id":"C-0123"}')])
    return reply(f"<answer>{json.loads(last['content'])['email']}</answer>")


ROW_FIELDS = {"model", "condition", "task_id", "trial", "success", "input_tokens", "output_tokens", "total_tokens", "model_turns", "tool_calls", "code_executions", "sandbox_errors", "wall_time_s", "timestamp", "error", "cache_hits", "cached_input_tokens", "truncated_outputs", "stop_reason", "final_answer"}


async def test_run_logs_schema_and_scores_through_real_servers(tmp_path: Path, base_dir: Path) -> None:
    client = FakeClient(answer_from_tools)
    await runner.amain(args_for(), client, tmp_path / "r", tmp_path / "c", base_dir)
    rows = runner.read_rows(tmp_path / "r" / "runs.jsonl")
    assert len(rows) == 1
    row = rows[0]
    assert ROW_FIELDS <= set(row)
    assert row["success"] is True and row["tool_calls"] == 1 and row["model_turns"] == 2 and row["total_tokens"] == 220
    assert len(client.requests[0]["tools"]) == 32
    meta = json.loads((tmp_path / "r" / "run_meta.json").read_text())
    assert meta["models"] == ["m1"] and meta["packages"]["mcp"] and meta["data_seed"]


async def test_each_run_sends_one_stable_session_id(tmp_path: Path, base_dir: Path) -> None:
    client = FakeClient(answer_from_tools)
    await runner.amain(args_for(trials=2), client, tmp_path / "r", tmp_path / "c", base_dir)
    sessions = [r["extra_headers"]["x-opencode-session"] for r in client.requests]
    assert len(sessions) == 4 and len(set(sessions)) == 2 and sessions.count(sessions[0]) == 2


async def test_wrong_answer_is_logged_as_failure(tmp_path: Path, base_dir: Path) -> None:
    await runner.amain(args_for(), FakeClient(lambda _: reply("<answer>nope</answer>")), tmp_path / "r", tmp_path / "c", base_dir)
    row = runner.read_rows(tmp_path / "r" / "runs.jsonl")[0]
    assert row["success"] is False and row["error"] is None


async def test_resume_skips_finished_runs(tmp_path: Path, base_dir: Path) -> None:
    client = FakeClient(answer_from_tools)
    await runner.amain(args_for(), client, tmp_path / "r", tmp_path / "c", base_dir)
    sent = len(client.requests)
    await runner.amain(args_for(), client, tmp_path / "r", tmp_path / "c", base_dir)
    assert len(client.requests) == sent
    assert len(runner.read_rows(tmp_path / "r" / "runs.jsonl")) == 1


async def test_trials_get_separate_requests(tmp_path: Path, base_dir: Path) -> None:
    client = FakeClient(answer_from_tools)
    await runner.amain(args_for(trials=3), client, tmp_path / "r", tmp_path / "c", base_dir)
    assert len(client.requests) == 6
    assert sorted(r["trial"] for r in runner.read_rows(tmp_path / "r" / "runs.jsonl")) == [1, 2, 3]


async def test_cap_stops_cleanly_and_a_rerun_finishes_from_the_cache(tmp_path: Path, base_dir: Path) -> None:
    client = FakeClient(answer_from_tools)
    await runner.amain(args_for(max_requests=1), client, tmp_path / "r", tmp_path / "c", base_dir)
    assert runner.read_rows(tmp_path / "r" / "runs.jsonl") == []
    assert len(client.requests) == 1
    await runner.amain(args_for(), client, tmp_path / "r", tmp_path / "c", base_dir)
    assert len(client.requests) == 2
    row = runner.read_rows(tmp_path / "r" / "runs.jsonl")[0]
    assert row["cache_hits"] == 1 and row["success"] is True


async def test_api_failure_is_logged_then_retried_only_on_request(tmp_path: Path, base_dir: Path) -> None:
    llm_args = args_for()
    failing = FakeClient(lambda _: status_error(401))
    await runner.amain(llm_args, failing, tmp_path / "r", tmp_path / "c", base_dir)
    assert runner.read_rows(tmp_path / "r" / "runs.jsonl")[0]["error"] == "api_error"

    await runner.amain(llm_args, failing, tmp_path / "r", tmp_path / "c", base_dir)
    assert len(runner.read_rows(tmp_path / "r" / "runs.jsonl")) == 1

    await runner.amain(args_for(retry_errors=True), FakeClient(answer_from_tools), tmp_path / "r", tmp_path / "c", base_dir)
    rows = runner.read_rows(tmp_path / "r" / "runs.jsonl")
    assert [r["error"] for r in rows] == ["api_error", None]


async def test_api_failure_detail_is_reported_with_the_key_redacted(tmp_path: Path, base_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "sk-secret")
    await runner.amain(args_for(), FakeClient(lambda _: status_error(403, "denied for sk-secret")), tmp_path / "r", tmp_path / "c", base_dir)
    err = capsys.readouterr().err
    assert "HTTP 403" in err and "denied" in err and "sk-secret" not in err


async def test_dry_run_retries_a_failed_row(tmp_path: Path, base_dir: Path) -> None:
    args = args_for(dry_run=True, approved=False)
    await runner.amain(args, FakeClient(lambda _: status_error(401)), tmp_path / "r", tmp_path / "c", base_dir)
    client = FakeClient(lambda _: reply("<answer>1</answer>"))
    await runner.amain(args, client, tmp_path / "r", tmp_path / "c", base_dir)
    assert len(client.requests) == 1


TIMEOUT = openai.APITimeoutError(request=httpx2.Request("POST", "http://fake"))
HUGE = [{"role": "tool", "content": "x" * (OVERSIZED_REQUEST_CHARS + 1)}]


@pytest.mark.parametrize("error", [TIMEOUT, status_error(504)])
async def test_oversized_request_gets_one_attempt(tmp_path: Path, error: Exception) -> None:
    client = FakeClient(lambda _: error)
    llm, sleeps = make_llm(client, tmp_path)
    with pytest.raises(OversizedRequestFailure):
        await llm.complete("m", 1, HUGE, [])
    assert len(client.requests) == 1 and sleeps == []


async def test_oversized_request_still_retries_rate_limits(tmp_path: Path) -> None:
    results = [status_error(429), reply("ok")]
    llm, sleeps = make_llm(FakeClient(lambda _: results.pop(0)), tmp_path)
    await llm.complete("m", 1, HUGE, [])
    assert len(sleeps) == 1


async def test_normal_timeout_is_still_retried(tmp_path: Path) -> None:
    results = [TIMEOUT, reply("ok")]
    llm, sleeps = make_llm(FakeClient(lambda _: results.pop(0)), tmp_path)
    assert (await llm.complete("m", 1, MESSAGES, [])).message["content"] == "ok"
    assert len(sleeps) == 1


async def test_oversized_failure_is_logged_and_not_rerun_by_retry_errors(tmp_path: Path, base_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("llm.OVERSIZED_REQUEST_CHARS", 1)
    client = FakeClient(lambda _: TIMEOUT)
    await runner.amain(args_for(), client, tmp_path / "r", tmp_path / "c", base_dir)
    row = runner.read_rows(tmp_path / "r" / "runs.jsonl")[0]
    assert row["success"] is False and row["error"] == "oversized_request" and len(client.requests) == 1
    await runner.amain(args_for(retry_errors=True), client, tmp_path / "r", tmp_path / "c", base_dir)
    assert len(client.requests) == 1


async def test_dry_run_can_use_another_task_and_ignores_old_rows(tmp_path: Path, base_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = args_for(dry_run=True, approved=False, tasks="all")
    await runner.amain(args, FakeClient(lambda _: status_error(401)), tmp_path / "r", tmp_path / "c", base_dir)
    capsys.readouterr()
    await runner.amain(args_for(dry_run=True, approved=False, tasks="S05"), FakeClient(answer_from_tools), tmp_path / "r", tmp_path / "c", base_dir)
    output = capsys.readouterr().out
    assert "A S05 m1" in output and "L01" not in output and "api_error" not in output


async def test_context_overflow_is_logged_as_failure(tmp_path: Path, base_dir: Path) -> None:
    await runner.amain(args_for(), FakeClient(lambda _: status_error(413)), tmp_path / "r", tmp_path / "c", base_dir)
    row = runner.read_rows(tmp_path / "r" / "runs.jsonl")[0]
    assert row["success"] is False and row["error"] == "context_overflow"


async def test_harness_failure_is_logged_as_internal(tmp_path: Path, base_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def broken(_: Any) -> Exposure:
        raise RuntimeError("bug with sk-secret")

    monkeypatch.setitem(runner.EXPOSURES, "A", broken)
    monkeypatch.setenv("OPENCODE_API_KEY", "sk-secret")
    await runner.amain(args_for(), FakeClient(lambda _: reply("x")), tmp_path / "r", tmp_path / "c", base_dir)
    assert runner.read_rows(tmp_path / "r" / "runs.jsonl")[0]["error"] == "internal"
    assert "sk-secret" not in capsys.readouterr().err


async def test_dry_run_uses_its_own_log_and_one_model(tmp_path: Path, base_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeClient(lambda _: reply("<answer>1</answer>"))
    await runner.amain(args_for(models="m1,m2", dry_run=True, approved=False, tasks="all"), client, tmp_path / "r", tmp_path / "c", base_dir)
    assert not (tmp_path / "r" / "runs.jsonl").exists()
    rows = runner.read_rows(tmp_path / "r" / "dry_runs.jsonl")
    assert [(r["model"], r["task_id"], r["trial"]) for r in rows] == [("m1", "L01", "dryrun")]
    output = capsys.readouterr().out
    assert "input tokens: 18,000" in output and "requests: 180" in output and "rough" in output


async def test_full_run_needs_approval(tmp_path: Path, base_dir: Path) -> None:
    client = FakeClient(lambda _: reply("x"))
    with pytest.raises(SystemExit):
        await runner.amain(args_for(approved=False), client, tmp_path / "r", tmp_path / "c", base_dir)
    assert client.requests == []


async def test_key_is_not_written_anywhere(tmp_path: Path, base_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "sk-secret-value")
    await runner.amain(args_for(), FakeClient(answer_from_tools), tmp_path / "r", tmp_path / "c", base_dir)
    for path in [*(tmp_path / "r").rglob("*"), *(tmp_path / "c").rglob("*")]:
        if path.is_file():
            assert "sk-secret-value" not in path.read_text()


async def test_list_models_prints_ids_and_sends_no_chat(tmp_path: Path, base_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeClient(lambda _: reply())

    async def list_models() -> SimpleNamespace:
        return SimpleNamespace(data=[SimpleNamespace(id="b"), SimpleNamespace(id="a")])

    client.models = SimpleNamespace(list=list_models)
    await runner.amain(args_for(list_models=True), client, tmp_path / "r", tmp_path / "c", base_dir)
    assert capsys.readouterr().out.split() == ["a", "b"] and client.requests == []
