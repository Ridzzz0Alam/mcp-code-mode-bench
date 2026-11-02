# M3 dry-run feedback (from the parallel opencode session, ~18:52)

Status observed from outside: `runner.py --dry-run --conditions A --max-requests 30`
(PID 155523 / 155527) has been running since 18:33 with 3 cached turns
(input 4,321 / 4,588 / 4,829) and no turn-4 response. Your 17:49 note says you are
leaving it to observe the endpoint behaviour. Points below are the parts that were
not in that note.

## 1. Plan rule for this exact case: no retries

PLAN.md section 4, "Condition A oversized results": do not truncate; if the context
exceeds the model's limit, end the run with `success=false`, `error="context_overflow"`,
and **do not retry this error**.

Right now the oversized case is reaching the generic connection-error path instead
(`llm.py` `except openai.APIConnectionError`, retried with backoff). So a single
unanswerable request is being attempted repeatedly, 5 minutes per attempt.

Please make the classification explicit:
- API rejects the request (400 / context length) -> `context_overflow`, no retry.
- API accepts then hangs until the client timeout -> still one logical outcome for
  this condition. Record it as `api_error` (or `context_overflow` if that is the
  better model of what happened) after **one** attempt, not after the full retry
  budget, and note the timeout in the run log / report.

A 5-minute timeout times 4 retries on a request that can never succeed is quota and
wall-clock spent on a result we already know.

## 2. Cost of waiting for the retries to exhaust

Each retry re-sends the ~2.3M-character prompt. Provider prompt caching was working
on turns 2-3 (cached_input_tokens 4,288 / 4,544), but do not assume it covers this
oversized request. If the only goal is to learn how the endpoint behaves, one attempt
answers it; the remaining retries add cost, not information.

## 3. M3 exit criteria if L01 cannot complete under condition A

M3 requires tokens plus an extrapolation. If condition A can never finish L01 when
the model chooses a full `read_rows`, that is a legitimate experimental result, but
it cannot produce the token numbers the extrapolation needs. Suggest reporting both:
- "condition A fails on L01 via oversized result" as the dry-run finding, and
- a rough extrapolation taken from a task that does complete, clearly labelled.

Do not change L01, the tools, or the prompts to make condition A pass; the freeze
rule and the spec's "do not assume the headline numbers reproduce" both apply.

## 4. Model choice (token-burn concern from the user)

The dry run uses `models[:1]`, currently `kimi-k3`, a heavy reasoning model. The user
is concerned about its token consumption. Cheaper candidates from the Go catalog,
all on the OpenAI chat-completions endpoint:
- `glm-5.3-flash` + `deepseek-v4.1-flash` (lowest token burn)
- `kimi-k2.7-code` + `deepseek-v4.1-flash` (keeps a Kimi, code-oriented for condition C)

Whichever pair is chosen must still pass the M3 checks: real tool calls and a `usage`
field on every response. Models are only frozen once the full run starts.

## 5. Housekeeping

`results/dry_runs.jsonl` currently holds two `api_error` rows with null usage from the
earlier header failures. They are dry-run rows so they do not affect resume logic, but
please make sure they are excluded from any reported numbers.

---

## Update 19:15 (user decision)

- The user set the workspace region to Global, then chose the **model swap** path anyway.
- `.env` now has `MODELS=glm-5.3-flash,kimi-k2.7-code` (DeepSeek replaced).
- `kimi-k2.7-code` was verified with a capped dry run on S05 (condition A):
  success=True, 2 turns, 1 tool call, input 5,882 / output 105 / total 5,987 tokens,
  wall 4.5 s, `usage` present on every response. 3 HTTP requests, 0 internal errors.
- Since Global is now enabled, DeepSeek may work too. If the spec's Kimi+DeepSeek
  pairing is preferred, reverting is a one-line change to `.env`.
- New dry-run rows for kimi-k2.7-code were appended to `results/dry_runs.jsonl`.

---
No code, data, tasks, or processes were changed by the other session; only this file
was added.
