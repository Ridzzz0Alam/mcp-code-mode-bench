# Decisions that affect fairness or interpretation

The deviations from the spec (D1 to D7) are in [PLAN.md](../PLAN.md), section 2. The ones below were made during the build.

## Decided by the human

- Models are `glm-5.3-flash` and `kimi-k2.7-code`.

## Made during the build, and open to review

### Tools and data

- **32 tools, not about 30.** `create_task` and `list_tasks` give multi-step tasks somewhere to write action items.
- **No server-side aggregation.** Sum or group-by tools would remove the effect under test. `find_rows` matches on one
  column only.
- **`read_rows` returns everything when `limit` is omitted.** Models may page in any condition, and no prompt suggests a strategy.
- **Compact JSON results.** Indented output would inflate condition A's token counts, so this choice favours A slightly
  if anything.

### Scoring

- **Strict checks in every condition.** Text answers must match exactly, money must be within $0.01, and CRM tasks fail
  on any stray or unrelated change. If success rates look very low, read the failed answers before blaming the models.
- **CRM tasks ignore the final message,** because the outcome is the final state.

### Failure handling

- **Condition A results are never truncated.**
- **`oversized_request`** is a new error value: a request over 500,000 characters that times out or gets a 5xx ends
  after one attempt. It counts as a failure in success rates, like `context_overflow`, and `--retry-errors` skips it.
  Excluding these runs would flatter condition A.
- **`api_error` and `internal` rows are excluded** from success rates and reported separately with a count.

### Condition C

- **Error output counts as output.** A failed script returns its traceback to the model, within the same 4,000-character
  limit. The spec mentions only printed output, but without this the model could not fix its code.
- **Standard library only.** No pandas in the sandbox, and the prompt says so. Adding it would give code mode an extra advantage.
- **`/workspace` persists within a run,** but Python variables do not.
- **Docker, with no network at all.** Tools are reached through a Unix socket served by a process on the host, which
  meets the spec's "no network except to the local MCP servers".
- **`wall_time_s` excludes rate-limit waits and server startup,** but includes container startup for C. Report the 0.25 s
  overhead with the latency results.

### Harness

- **`--approved` flag:** a non-dry run refuses to start without it. This is an addition to the spec, as a safeguard.
- **Cached replays report original usage and latency,** so a resumed run reports true values.
