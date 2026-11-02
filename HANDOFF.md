# Handoff: start here

For any AI agent continuing this project with no earlier context. Last updated 2026-11-02, at the end of M4.

Update this file whenever a milestone changes state or a decision is made.

## Where things stand

| Milestone | Scope | State |
|---|---|---|
| M0 | Scaffold | Done |
| M1 | Fake data, mock MCP servers, tool tests | Done |
| M2 | 30 tasks, checkers, oracle | Done |
| M3 | Condition A, runner, cache, logging | Done |
| M4 | Condition C, sandbox | Done, **awaiting human review** |
| M5 | Condition B, dry run of all three | Not started |
| M6 | Full run, analysis, figures | Not started, needs explicit cost approval |

All 311 tests passed at the end of M4. Run them with `uv run pytest -q`; this takes about 4 minutes and needs
Docker. **Nothing has been committed.** The git repository has no commits, and the human has not asked for any.

## Read these, in order

1. [EXPERIMENT_SPEC.md](EXPERIMENT_SPEC.md): what to measure.
2. [PLAN.md](PLAN.md): how to build it, the hard rules, and the deviations from the spec.
3. [findings/README.md](findings/README.md): what has been learned so far, including measured numbers.
4. [M3_FEEDBACK.md](M3_FEEDBACK.md): feedback from a parallel session. Its requests are already handled.

## Rules that are easy to break

- **Stop after each milestone** for human review. Do not start M5 until the human approves M4.
- **Model API calls only through `runner.py`**, as a dry run or a full run the human approved. Tests use a fake client.
- **A full run needs explicit human approval of the cost.** The runner enforces this with `--approved`. Never pass
  that flag on your own judgment.
- **Never print, log, or copy `OPENCODE_API_KEY`.** To inspect `.env`, print only variable names or the `MODELS` line.
- **Do not change tasks, tools, or prompts to make a condition pass.**
- **Report results as measured**, including ones that contradict the source post.

## Next step: M5, once the human approves

1. Write `agents/tool_search.py` with a `ToolSearchExposure(Exposure)`, following `agents/direct.py`:
   - The model starts with only `search_tools(query)`.
   - Search is deterministic BM25 (`rank-bm25` is installed) over tool name and description, returning the top 5.
   - The result lists names and one-line summaries. Full schemas join `tools()` from the next request and stay loaded.
   - Results are returned verbatim, as in condition A.
   - Calling a tool that is not loaded returns a clear error.
2. Register it in `EXPOSURES` in `runner.py` as `"B"`.
3. Test deterministic ranking, schema persistence, and the not-loaded error. Confirm the system prompt core is
   byte-identical across conditions (`SYSTEM_CORE` in `agents/common.py`).
4. Dry-run, capped, and report per-run numbers:
   ```
   uv run python runner.py --dry-run --conditions B --models glm-5.3-flash --tasks L01 --max-requests 30
   uv run python runner.py --dry-run --conditions A --models kimi-k2.7-code --tasks L01 --max-requests 30
   ```
   The Kimi run under condition A is required: the current cost estimate comes from GLM alone. Also try at least one
   `simple` task under C, because none has been run yet and that is where code mode may lose.
5. Build a blended, per-category estimate for the full run and **wait for approval**. See "Traps" for why the runner's
   printed extrapolation is not enough.

## Before the full run (M6)

- Fix `results/run_meta.json`: every invocation overwrites it, including dry runs, and `temperature_dropped_for` only
  covers the current process.
- Raise the Opencode Go usage question with the human (see "Open items").
- Run in batches with `--max-requests`, and stop and report if any `internal` error appears.
- `analysis/report.py` does not exist yet. Its requirements are in spec section 8 and PLAN.md M6.

## Project map

| Path | Purpose |
|---|---|
| `runner.py` | CLI and the only code that may call the model API |
| `llm.py` | Client, on-disk cache, retries, request cap, error classification |
| `agents/common.py` | Shared agent loop, `SYSTEM_CORE`, the `Exposure` base class |
| `agents/direct.py`, `agents/code_mode.py` | Conditions A and C |
| `servers/{sheets,docs,crm}.py` | Mock MCP servers, 32 tools |
| `servers/client.py` | The one MCP client layer that every condition and the oracle use |
| `servers/state.py` | Data paths, per-run CRM state, `FAKE_TODAY` |
| `sandbox/` | Dockerfile, host-side socket gateway, container executor |
| `toolpkg_gen.py`, `toolpkg/` | Generator and generated package for condition C |
| `data/generate.py` | Seeded data generator. Its output is gitignored |
| `tasks/build_tasks.py` | Computes expected answers and writes `tasks/tasks.jsonl` |
| `tasks/checkers.py`, `tasks/oracle.py` | Programmatic checkers and scripted solutions |
| `results/dry_runs.jsonl` | Dry-run log, gitignored. Numbers are copied to `findings/` |

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
- **M4 review:** the fairness decisions awaiting review are in [findings/03-decisions.md](findings/03-decisions.md).
