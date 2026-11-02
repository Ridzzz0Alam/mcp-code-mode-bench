# Experiment spec: Code execution with MCP vs. direct tool calling

Source post: Anthropic, "Code execution with MCP: Building more efficient agents"
https://www.anthropic.com/engineering/code-execution-with-mcp

## 1. Question

When an agent has many MCP tools and some return large outputs, does letting the model
write code against the tools (code mode) reduce tokens and latency compared with
classic direct tool calling, without lowering task success? And which of the two effects
in the post matters more:
(a) loading tool definitions on demand, or
(b) filtering/aggregating tool results in a sandbox before they reach the model?

Do not assume the post's headline numbers will reproduce; measure them.

## 2. Conditions (same tasks, same models)

- **A. Direct**: all tool schemas sent in every request; every tool result goes back into the context verbatim.
- **B. Tool search**: direct tool calling, but the model starts with only `search_tools(query)` and loads
  matching tool schemas on demand. Isolates effect (a).
- **C. Code mode**: tools exposed as a generated Python package (one module per tool, with docstring).
  The model can list/read those files, then submits Python that is run in a sandbox; only what the code
  prints (truncated to 4,000 chars) returns to the model. Tests (a) + (b).

## 3. Environment

- Two or three **mock MCP servers** built with the official MCP Python SDK, about 30 tools in total,
  backed by seeded, deterministic fake data (fixed random seed, generated once into `data/`):
  - `sheets`: spreadsheets of 50 to 10,000 rows (orders, customers, inventory)
  - `docs`: documents with long text (meeting notes, policies)
  - `crm`: contacts, deals, notes (read and write)
  - include several tools with long, realistic descriptions and parameter schemas
- No real external services, no network access from the sandbox except to the local MCP servers.
- **Sandbox** for condition C: run submitted code in a Docker container (or a subprocess) with a
  30-second timeout, memory limit, no internet, read-only mount of the generated tool package.

## 4. Tasks

30 tasks in `tasks/tasks.jsonl`, each with a programmatic checker (no LLM judging):

- 12 **large-data** tasks (filter/aggregate a 10k-row sheet, find records matching criteria)
- 10 **multi-step** tasks (read a doc, extract items, write them to CRM; chain 3+ tools)
- 8 **simple** tasks (one or two small tool calls), where code mode may be worse

Each task: `id`, `category`, `prompt`, `checker` (function name), expected answer or expected final state.
Reset the mock data state before every run.

## 5. Models and API

- All model calls go through Opencode Go's OpenAI-compatible endpoint using the `openai` Python SDK.
- Config only via environment variables in `.env` (gitignored): `OPENCODE_BASE_URL`, `OPENCODE_API_KEY`,
  `MODELS` (comma-separated model IDs). Never hard-code or log the key.
- Get exact model IDs from `GET {OPENCODE_BASE_URL}/models`; use 2 models (e.g. one Kimi, one DeepSeek).
- Temperature 0 if supported. Max 25 model turns per task.

## 6. Metrics (log one JSON line per run to `results/runs.jsonl`)

model, condition, task_id, trial, success (bool), input_tokens, output_tokens, total_tokens,
model_turns, tool_calls, code_executions, sandbox_errors, wall_time_s, timestamp, error.
Token counts come from the API `usage` field, not estimates.

3 trials per (model, condition, task) = 2 x 3 x 30 x 3 = 540 runs.

## 7. Cost and rate-limit safety

- **Cache** every request/response on disk keyed by hash(model, messages, tools); reruns hit the cache.
- `--dry-run` mode: run 1 task per condition with 1 model, print tokens used and extrapolate the full cost.
- `--max-requests N` hard cap per invocation; stop cleanly when reached.
- Concurrency limit of 2; on HTTP 429/5xx use capped exponential backoff with full jitter, max 4 retries,
  then mark the run as `error` and continue.
- Runs must be resumable: skip (model, condition, task, trial) rows already in `runs.jsonl`.

## 8. Analysis

`analysis/report.ipynb` (or `report.py`) producing:
- success rate per condition x model (with per-category breakdown)
- median and p90 total tokens per condition, split by task category
- tokens vs. success scatter, one point per run
- latency per condition
- a short table of failure modes found in condition C (bad code, sandbox errors, truncated output)
Save charts as PNG in `results/figures/`.

## 9. Suggested repo layout

```
mcp-code-exec-experiment/
  EXPERIMENT_SPEC.md
  .env.example
  data/                 # generated fake data
  servers/              # mock MCP servers
  toolpkg/              # generated Python wrappers for condition C
  tasks/tasks.jsonl
  tasks/checkers.py
  agents/direct.py      # condition A
  agents/tool_search.py # condition B
  agents/code_mode.py   # condition C
  sandbox/
  runner.py             # CLI: --models --conditions --tasks --trials --dry-run --max-requests
  cache/
  results/
  analysis/
  tests/
```

## 10. Milestones (stop after each one for review)

1. Fake data generator + mock MCP servers + unit tests for every tool.
2. 30 tasks + checkers, verified by a scripted "oracle" solution for each task (no LLM).
3. Condition A agent + runner + cache + logging; run `--dry-run`.
4. Condition C (tool package generator, sandbox, code-mode agent); run `--dry-run`.
5. Condition B agent; run `--dry-run` for all three.
6. Full run (after I confirm the dry-run cost), then analysis and figures.

## 11. Rules for the coding agent

- Python 3.11+, `uv` or `pip` + `requirements.txt`, type hints, `pytest`.
- Keep the three agents as similar as possible; differences only in how tools are exposed.
- Same system prompt core for all conditions; put condition-specific instructions in a clearly separated block.
- Do not call the Opencode Go API outside `runner.py --dry-run` or a full run I approved.
- Record exact package versions and model IDs in `results/run_meta.json`.
