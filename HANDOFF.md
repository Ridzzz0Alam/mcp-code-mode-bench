# Handoff: start here

For any AI agent continuing this project with no earlier context. Last updated 2026-11-02, at the end of M5.

Update this file whenever a milestone changes state or a decision is made.

## Where things stand

| Milestone | Scope | State |
|---|---|---|
| M0 | Scaffold | Done |
| M1 | Fake data, mock MCP servers, tool tests | Done |
| M2 | 30 tasks, checkers, oracle | Done |
| M3 | Condition A, runner, cache, logging | Done |
| M4 | Condition C, sandbox | Done |
| M5 | Condition B, dry run of all three | Done |
| M6 | Full run, analysis, figures | Not started. **Waiting on the human's decision below** |

All 328 tests pass. Run them with `uv run pytest -q`; this takes about 6 minutes and needs
Docker. **Nothing has been committed.** The git repository has no commits, and the human has not asked for any.

## Read these, in order

1. [EXPERIMENT_SPEC.md](EXPERIMENT_SPEC.md): what to measure.
2. [PLAN.md](PLAN.md): how to build it, the hard rules, and the deviations from the spec.
3. [findings/README.md](findings/README.md): what has been learned so far, including measured numbers.
4. [M3_FEEDBACK.md](M3_FEEDBACK.md): feedback from a parallel session. Its requests are already handled.

## Rules that are easy to break

- **Stop after each milestone** for human review. Do not start the full run until the human approves its cost.
- **Model API calls only through `runner.py`**, as a dry run or a full run the human approved. Tests use a fake client.
- **A full run needs explicit human approval of the cost.** The runner enforces this with `--approved`. Never pass
  that flag on your own judgment.
- **Never print, log, or copy `OPENCODE_API_KEY`.** To inspect `.env`, print only variable names or the `MODELS` line.
- **Do not change tasks, tools, or prompts to make a condition pass.**
- **Report results as measured**, including ones that contradict the source post.

## Where the conversation stopped

No run is in progress. The human has **not approved any full or pilot run**. They raised concern about token use, and
said their current 5-hour usage window is nearly used up, so nothing should run for now.

Recommended next step, proposed but not yet accepted: **a pilot on `glm-5.3-flash`, 1 trial, all 30 tasks and all 3
conditions**, about 90 runs, 30M tokens, and $2.50 of plan allowance, started on a fresh usage window. Pilot rows count
as trial 1, so continuing later reuses them. The options, including using an OpenAI key, are in
[findings/05-cost-options.md](findings/05-cost-options.md).

## Before any run

Ask the human for all of these:

1. Approval of the pilot or another option.
2. Confirmation that their usage window has reset. The limits are per model according to the docs, so the console should
   show each model's state.
3. Confirmation that pay-as-you-go fallback is off.
4. Acceptance of the Opencode Go usage risk (see "Open items").

Then finish this prep, which makes no model API calls. The human has so far asked only for the first item:

- [x] `results/run_meta.json` describes the actual run. Dry runs use `results/dry_run_meta.json`.
- [ ] Make the runner stop cleanly at a usage limit. How the API responds at a limit is unknown. If it returns errors,
      every remaining run could fail fast and be logged as `api_error`. Those can be rerun with `--retry-errors`.
- [ ] Write `analysis/report.py` (spec section 8, PLAN.md M6) and test it on fake results. Load the `dataviz` skill before charting.

## Pilot command, only after approval

```
uv run python runner.py --approved --models glm-5.3-flash --conditions A,B,C --tasks all --trials 1 --max-requests 300
```

Rerun the same command to continue each batch. A full 3-trial run later uses the same command with `--trials 3`.

During the run:

- Stop and report if any `internal` error appears.
- Check the first `context_overflow` message on stderr. The Kimi dry-run overflow was classified by a broad text
  pattern in `llm.py` before messages were reported, so it is unproven.
- Check `environment_changed` in `results/run_meta.json`. It should stay `false` within a run set.
- Expect usage windows to interrupt Kimi: its 5-hour allowance is $12 on the Go plan.

A git commit before the pilot would make `git_commit` in the metadata useful, but commit only if the human asks.

## Project map

| Path | Purpose |
|---|---|
| `runner.py` | CLI and the only code that may call the model API |
| `llm.py` | Client, on-disk cache, retries, request cap, error classification |
| `agents/common.py` | Shared agent loop, `SYSTEM_CORE`, the `Exposure` base class |
| `agents/direct.py`, `agents/tool_search.py`, `agents/code_mode.py` | Conditions A, B and C |
| `servers/{sheets,docs,crm}.py` | Mock MCP servers, 32 tools |
| `servers/client.py` | The one MCP client layer that every condition and the oracle use |
| `servers/state.py` | Data paths, per-run CRM state, `FAKE_TODAY` |
| `sandbox/` | Dockerfile, host-side socket gateway, container executor |
| `toolpkg_gen.py`, `toolpkg/` | Generator and generated package for condition C |
| `data/generate.py` | Seeded data generator. Its output is gitignored |
| `tasks/build_tasks.py` | Computes expected answers and writes `tasks/tasks.jsonl` |
| `tasks/checkers.py`, `tasks/oracle.py` | Programmatic checkers and scripted solutions |
| `results/dry_runs.jsonl`, `results/dry_run_meta.json` | Dry-run log and metadata. The log is gitignored, and its numbers are copied to `findings/` |
| `results/runs.jsonl`, `results/run_meta.json` | Real run log and metadata. Neither exists until a run is approved |

## Setup and commands

`.env` holds `OPENCODE_BASE_URL`, `OPENCODE_API_KEY`, and `MODELS=glm-5.3-flash,kimi-k2.7-code`.

```
uv run python data/generate.py          # recreate data/ if missing
uv run python tasks/build_tasks.py      # after any data change
uv run python toolpkg_gen.py            # after any tool change
docker build -t bench-sandbox:1 sandbox/
uv run pytest -q
```

## Traps

- **MCP SDK is 2.x:** use `MCPServer`, not `FastMCP`. A tool returning a list becomes one content block per item, so
  every tool here returns one compact JSON string with `structured_output=False`.
- **MCP client lifetime:** `open_tools` must enter and exit in the same asyncio task. Exceptions leaving it arrive as
  an `ExceptionGroup`, so `run_one` handles `RequestCapReached` inside the context.
- **OpenAI SDK:** `max_retries=0` is deliberate, because SDK retries would get past `--max-requests`.
- **Opencode Go headers:** requests need `x-opencode-session`, one stable ID per run, and an honest user agent.
- **Reasoning fields:** `reasoning_content` must be sent back on later turns. `_message_dict` keeps it.
- **Unix socket paths** are limited to about 108 characters, so condition C run folders live directly under `/tmp`.
- **Dry-run extrapolation:** the runner multiplies one task's tokens by every run. That is wildly high when the task is
  L01 and low when it is simple, so build the estimate per category by hand.
- **Dry-run resume:** a finished row is skipped on rerun. Only `api_error` rows are retried.
- **Cache key includes `trial`** on purpose (PLAN.md D1). Do not remove it.
- **`data/` is gitignored but `tasks/tasks.jsonl` is not:** a test fails if they stop matching.

## Open items for the human

- **Key rotation:** the original API key appeared in `.env.example` and in a session's context, and has been removed
  from the file. Whether it has been rotated has not been confirmed.
- **Opencode Go usage:** the docs say Go is designed for coding agents and that traffic is monitored for abuse. They
  neither allow nor ban a benchmark script. The human should accept this risk before a full run, and check that the
  run fits the plan's limits. Details are in [findings/02-endpoint-and-models.md](findings/02-endpoint-and-models.md).
- **Base URL:** `.env` uses `opencode.ai/zen/go/v1`, while the docs list `opencode.ai/inference/go/openai/v1`. The
  current one works, so it was left alone.
- **Run approval:** pending, see "Where the conversation stopped". The fairness decisions are in
  [findings/03-decisions.md](findings/03-decisions.md).
- **`M3_FEEDBACK.md`:** the human may edit this file to pass notes from a parallel session, so check it for updates.
