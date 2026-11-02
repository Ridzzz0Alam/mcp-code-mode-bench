"""Experiment CLI. This is the only code allowed to call the model API.

  runner.py --list-models
  runner.py --dry-run --conditions A
  runner.py --approved --conditions A,B,C --tasks all --trials 3 --max-requests 500
"""

import argparse
import asyncio
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

from agents.code_mode import CodeExposure
from agents.common import Exposure, run_agent, usage_totals
from agents.direct import DirectExposure
from agents.tool_search import ToolSearchExposure
from data.generate import SEED
from llm import LLM, REQUEST_TIMEOUT_S, RequestCapReached
from sandbox.executor import IMAGE
from servers.client import ToolClient, open_tools
from servers.state import ROOT, data_dir, new_run_state
from tasks.build_tasks import load_tasks
from tasks.checkers import check

CONCURRENCY = 2
USER_AGENT = "mcp-code-mode-bench/0.1"
DRY_RUN_TASK = "L01"
FULL_RUNS_PER_CONDITION = 2 * 30 * 3
DRY_RUN_MAX_REQUESTS = 60
ENVIRONMENT_FIELDS = ["sandbox_image", "packages", "python", "git_commit"]
PACKAGES = ["openai", "mcp", "pydantic", "pandas", "matplotlib", "rank-bm25"]
EXPOSURES: dict[str, Callable[[ToolClient], Exposure]] = {"A": DirectExposure, "B": ToolSearchExposure, "C": CodeExposure}


@dataclass
class Settings:
    models: list[str]
    conditions: list[str]
    tasks: list[dict[str, Any]]
    trials: list[int | str]
    results_dir: Path
    log_name: str
    retry_errors: bool = False
    meta_name: str = "run_meta.json"


def _redact(text: str) -> str:
    key = os.environ.get("OPENCODE_API_KEY")
    return text.replace(key, "[redacted]") if key else text


def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def finished_keys(path: Path, retry_errors: bool) -> set[tuple[str, str, str, int | str]]:
    latest = {(r["model"], r["condition"], r["task_id"], r["trial"]): r for r in read_rows(path)}
    return {key for key, row in latest.items() if not (retry_errors and row["error"] == "api_error")}


async def run_one(llm: LLM, model: str, condition: str, task: dict[str, Any], trial: int | str, base: Path) -> dict[str, Any]:
    """Run one task with fresh state. RequestCapReached passes through so no row is written."""
    base_crm = json.loads((base / "crm.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as temp:
        state_dir = new_run_state(Path(temp) / "state", base)
        async with open_tools(state_dir, base) as client:
            exposure = EXPOSURES[condition](client)
            try:
                await exposure.start()
                session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{USER_AGENT}/{model}/{condition}/{task['id']}/{trial}"))
                outcome = await run_agent(llm, model, trial, exposure, task["prompt"], session_id)
            except RequestCapReached as cap:
                # The MCP client's task group would wrap this in an ExceptionGroup on exit.
                return {"_cap": str(cap)}
            finally:
                await exposure.close()
            tool_calls = len(client.calls)
        if outcome.error_detail:
            print(f"{outcome.error} in {model}/{condition}/{task['id']}/{trial}: {_redact(outcome.error_detail)[:500]}", file=sys.stderr)
        state =json.loads((state_dir / "crm.json").read_text(encoding="utf-8"))
    success = outcome.error is None and check(task, outcome.final_message, state, base_crm)
    return {
        "model": model,
        "condition": condition,
        "task_id": task["id"],
        "category": task["category"],
        "trial": trial,
        "success": success,
        **usage_totals(outcome.usages),
        "model_turns": outcome.model_turns,
        "tool_calls": tool_calls,
        "code_executions": exposure.code_executions,
        "sandbox_errors": exposure.sandbox_errors,
        "wall_time_s": round(outcome.wall_time_s, 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": outcome.error,
        "cache_hits": outcome.cache_hits,
        "truncated_outputs": exposure.truncated_outputs,
        "stop_reason": outcome.stop_reason,
        "final_answer": outcome.final_message,
    }


async def execute(settings: Settings, llm: LLM, base: Path) -> dict[str, int | bool]:
    settings.results_dir.mkdir(parents=True, exist_ok=True)
    log = settings.results_dir / settings.log_name
    done = finished_keys(log, settings.retry_errors)
    pending = [
        (model, condition, task, trial)
        for model in settings.models
        for condition in settings.conditions
        for task in settings.tasks
        for trial in settings.trials
        if (model, condition, task["id"], trial) not in done
    ]
    semaphore = asyncio.Semaphore(CONCURRENCY)
    summary: dict[str, int | bool] = {"skipped": len(done), "written": 0, "cap_reached": False, "internal_errors": 0}

    async def worker(model: str, condition: str, task: dict[str, Any], trial: int | str) -> None:
        async with semaphore:
            if summary["cap_reached"]:
                return
            try:
                row = await run_one(llm, model, condition, task, trial, base)
            except Exception as error:
                print(f"internal error in {model}/{condition}/{task['id']}/{trial}: {_redact(repr(error))[:500]}", file=sys.stderr)
                row = {"model": model, "condition": condition, "task_id": task["id"], "category": task["category"], "trial": trial, "success": False, "error": "internal", "stop_reason": "internal", "timestamp": datetime.now(timezone.utc).isoformat()}
                summary["internal_errors"] += 1
            if "_cap" in row:
                summary["cap_reached"] = True
                return
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            summary["written"] += 1

    await asyncio.gather(*(worker(*item) for item in pending))
    return summary


def merge_meta(previous: dict[str, Any], invocation: dict[str, Any], temperature_dropped: set[str]) -> dict[str, Any]:
    """Combine this invocation with earlier ones, so resuming in batches loses no history."""
    invocations = [*previous.get("invocations", []), invocation]
    environments = {json.dumps({key: run[key] for key in ENVIRONMENT_FIELDS}, sort_keys=True) for run in invocations}
    return {
        **{key: invocation[key] for key in ENVIRONMENT_FIELDS},
        "data_seed": SEED,
        "first_started": invocations[0]["started"],
        "models": list(dict.fromkeys(model for run in invocations for model in run["models"])),
        "conditions": list(dict.fromkeys(condition for run in invocations for condition in run["conditions"])),
        "temperature_dropped_for": sorted(set(previous.get("temperature_dropped_for", [])) | temperature_dropped),
        # True means the runs did not all use the same code, packages or sandbox image.
        "environment_changed": len(environments) > 1,
        "invocations": invocations,
    }


def write_meta(settings: Settings, llm: LLM, started: str, summary: dict[str, int | bool]) -> None:
    revision = subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    commit = revision.stdout.strip() if revision.returncode == 0 else None
    image = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE], capture_output=True, text=True).stdout.strip() if "C" in settings.conditions else None
    invocation = {
        "started": started,
        "finished": datetime.now(timezone.utc).isoformat(),
        "models": settings.models,
        "conditions": settings.conditions,
        "http_requests": llm.requests_sent,
        "rows_written": summary["written"],
        "cap_reached": summary["cap_reached"],
        "sandbox_image": image or None,
        "packages": {name: importlib.metadata.version(name) for name in PACKAGES},
        "python": sys.version.split()[0],
        "git_commit": commit,
    }
    path = settings.results_dir / settings.meta_name
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.write_text(json.dumps(merge_meta(previous, invocation, llm.temperature_dropped), indent=2) + "\n", encoding="utf-8")


def _price(name: str) -> float | None:
    value = os.environ.get(name, "").strip()
    return float(value) if value else None


def dry_run_report(rows: list[dict[str, Any]]) -> str:
    lines = ["Dry-run results (1 task per condition, so the extrapolation is rough, and only as typical as that task):"]
    grand_in = grand_out = requests = 0
    known = True
    for row in rows:
        lines.append(
            f"  {row['condition']} {row['task_id']} {row['model']}: success={row['success']} error={row['error']} "
            f"turns={row.get('model_turns')} tool_calls={row.get('tool_calls')} input={row.get('input_tokens')} "
            f"output={row.get('output_tokens')} total={row.get('total_tokens')} cached={row.get('cached_input_tokens')} wall={row.get('wall_time_s')}s"
        )
        if row.get("input_tokens") is None or row.get("output_tokens") is None:
            known = False
        else:
            grand_in += row["input_tokens"]
            grand_out += row["output_tokens"]
        requests += row.get("model_turns") or 0
    lines.append(f"Extrapolated to {FULL_RUNS_PER_CONDITION} runs per condition:")
    lines.append(f"  requests: {requests * FULL_RUNS_PER_CONDITION:,}")
    if not known:
        lines.append("  tokens: unknown, because usage was missing from at least one run")
        return "\n".join(lines)
    input_tokens, output_tokens = grand_in * FULL_RUNS_PER_CONDITION, grand_out * FULL_RUNS_PER_CONDITION
    lines.append(f"  input tokens: {input_tokens:,}\n  output tokens: {output_tokens:,}")
    price_in, price_out = _price("PRICE_INPUT_PER_MTOK"), _price("PRICE_OUTPUT_PER_MTOK")
    if price_in is not None and price_out is not None:
        lines.append(f"  estimated cost: ${(input_tokens * price_in + output_tokens * price_out) / 1_000_000:,.2f}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", help="Comma-separated model IDs. Defaults to MODELS in .env.")
    parser.add_argument("--conditions", default="A,B,C")
    parser.add_argument("--tasks", default="all", help="'all' or comma-separated task IDs")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--retry-errors", action="store_true", help="Rerun rows whose error is api_error")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--approved", action="store_true", help="Required for a non-dry run: the human approved the cost")
    return parser


def make_client() -> AsyncOpenAI:
    base_url, api_key = os.environ.get("OPENCODE_BASE_URL"), os.environ.get("OPENCODE_API_KEY")
    if not base_url or not api_key:
        sys.exit("OPENCODE_BASE_URL and OPENCODE_API_KEY must be set in .env")
    # The SDK's own retries are disabled so that every HTTP request counts toward --max-requests.
    return AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=REQUEST_TIMEOUT_S, default_headers={"User-Agent": USER_AGENT})


def settings_from_args(args: argparse.Namespace, results_dir: Path) -> Settings:
    models = [m.strip() for m in (args.models or os.environ.get("MODELS", "")).split(",") if m.strip()]
    if not models:
        sys.exit("No models given. Set MODELS in .env or pass --models.")
    conditions = [c.strip() for c in args.conditions.split(",")]
    unknown = [c for c in conditions if c not in EXPOSURES]
    if unknown:
        sys.exit(f"Conditions not implemented: {unknown}")
    tasks = load_tasks()
    if args.dry_run:
        task_id = DRY_RUN_TASK if args.tasks == "all" else args.tasks
        chosen = [t for t in tasks if t["id"] == task_id]
        if not chosen:
            sys.exit(f"A dry run takes one task ID, not '{task_id}'")
        return Settings(models[:1], conditions, chosen, ["dryrun"], results_dir, "dry_runs.jsonl", retry_errors=True, meta_name="dry_run_meta.json")
    if not args.approved:
        sys.exit("A full run needs --approved, after the human has confirmed the dry-run cost.")
    if args.tasks != "all":
        wanted = set(args.tasks.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]
    return Settings(models, conditions, tasks, list(range(1, args.trials + 1)), results_dir, "runs.jsonl", args.retry_errors)


async def amain(args: argparse.Namespace, client: Any, results_dir: Path, cache_dir: Path, base: Path) -> int:
    if args.list_models:
        for model in sorted(m.id for m in (await client.models.list()).data):
            print(model)
        return 0
    settings = settings_from_args(args, results_dir)
    max_requests = args.max_requests if args.max_requests is not None else (DRY_RUN_MAX_REQUESTS if args.dry_run else None)
    llm = LLM(client, cache_dir, max_requests)
    started = datetime.now(timezone.utc).isoformat()
    summary = await execute(settings, llm, base)
    write_meta(settings, llm, started, summary)
    print(f"Written {summary['written']}, skipped {summary['skipped']}, HTTP requests {llm.requests_sent}, internal errors {summary['internal_errors']}.")
    if summary["cap_reached"]:
        print(f"Stopped at the limit of {max_requests} requests. Rerun to resume; unfinished runs replay from the cache.")
    if args.dry_run:
        # Only the latest row per key counts, so earlier failed attempts stay out of the numbers.
        wanted = {(c, settings.tasks[0]["id"], settings.models[0]) for c in settings.conditions}
        latest = {(r["condition"], r["task_id"], r["model"]): r for r in read_rows(results_dir / settings.log_name)}
        print(dry_run_report([latest[key] for key in sorted(wanted) if key in latest]))
    return 0


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = build_parser().parse_args()
    return asyncio.run(amain(args, make_client(), ROOT / "results", ROOT / "cache", data_dir()))


if __name__ == "__main__":
    sys.exit(main())
