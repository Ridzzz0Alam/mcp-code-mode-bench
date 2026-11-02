# Dry-run results

Each row is a single run, so these numbers show that the pipeline works and give a sense of scale. They are not
experiment results. Raw rows are in `results/dry_runs.jsonl`, which is gitignored.

## All completed runs

Correct L01 answer: $6,206,538.71.

| Model | Task | Cond. | Result | Turns | Tool calls | Code runs | Input | Output | Total | Cached input | Time |
|---|---|---|---|---|---|---|---|---|---:|---|---|
| glm-5.3-flash | L01 | A | Wrong: $6,138,850.55 | 7 | 9 | n/a | 1,207,338 | 12,034 | 1,219,372 | 788,800 | 215 s |
| glm-5.3-flash | L01 | C | Correct | 7 | 7 | 3 | 7,877 | 267 | 8,144 | 2,176 | 16 s |
| kimi-k2.7-code | L01 | C | Correct | 9 | 5 | 5 | 14,820 | 1,112 | 15,932 | not reported | 34 s |
| glm-5.3-flash | M01 | A | Correct | 4 | 5 | n/a | 26,333 | 304 | 26,637 | 16,320 | 9 s |
| glm-5.3-flash | M01 | C | Correct | 8 | 6 | 4 | 15,233 | 515 | 15,748 | 7,616 | 23 s |
| kimi-k2.7-code | S05 | A | Correct | 2 | 1 | n/a | 5,882 | 105 | 5,987 | not reported | 4.5 s |
| glm-5.3-flash | L01 | B | Wrong: $6,723,163.68 | 10 | 5 | n/a | 1,164,565 | 17,010 | 1,181,575 | 687,616 | 238 s |
| kimi-k2.7-code | L01 | A | `context_overflow` | 6 | 7 | n/a | 251,659 | 3,640 | 255,299 | not reported | 168 s |
| glm-5.3-flash | M01 | B | Correct | 5 | 5 | n/a | 17,087 | 333 | 17,420 | 9,792 | 9 s |
| glm-5.3-flash | S05 | B | Correct | 3 | 1 | n/a | 3,022 | 48 | 3,070 | 1,088 | 3 s |
| glm-5.3-flash | S05 | C | Correct | 5 | 1 | 1 | 3,515 | 85 | 3,600 | 0 | 6 s |
| kimi-k2.7-code | S05 | C | Correct | 5 | 1 | 1 | 3,204 | 239 | 3,443 | not reported | 11 s |

The Kimi S05 run was made by a parallel session and checked against the log afterwards.

## Incomplete or failed attempts

- **kimi-k3, L01, A:** the model's third turn called `read_rows` on orders with no limit, about 2.3 million characters.
  The next request got no response in about 22 minutes, so the process was stopped by hand. No row was logged. Before
  the stop, turns used 4,321, 4,588, and 4,829 input tokens. How the endpoint would have ended it was not established,
  and the quota those attempts used is unknown.
- **deepseek-v4.1-flash, S05, A:** refused with "This Go model requires Global regions".
- **Two earlier kimi-k3 rows** in `results/dry_runs.jsonl` are `api_error` rows from the missing session header. Exclude
  them from any numbers.

## What stands out, with caveats

- **L01 on GLM:** C used about 150 times fewer tokens than A and got the right answer, while A was about 1% off. This
  is one run of each.
- **A on large data depends on the model's choice.** GLM fetched columns and filtered rows, and its context reached
  414,534 input tokens by its last turn. kimi-k3 read the whole sheet and never got a reply. The two runs also differ
  by model, so this does not isolate the effect of that choice.
- **M01 shows the tradeoff.** C took about 40% fewer tokens but twice the turns and more than twice the time.
- **Tool search did not help on L01.** B used about as many tokens as A (1.18M against 1.22M), which fits the idea that data, not schemas, drives the cost on that task. One run.
- **Simple tasks cost about the same under C in tokens but take longer.** On Kimi S05, C used 3,443 tokens against A's 5,987, but 5 turns against 2 and 11 s against 4.5 s. The spec expected C might lose here; on tokens it did not in this one run.
- **Overflow rows undercount tokens.** A rejected request reports no usage, so Kimi's L01 row counts only completed turns. Report token medians for all runs and for successful runs.
- **Tool definitions are small here.** All 32 schemas are 19,215 characters, or about 5,000 tokens at a rough 4
  characters per token. Condition B may therefore save little next to the data effect. That follows from the spec's
  30-tool size, and the report should state it as a limit on how far results generalise.

## Scale of tool output

| Item | Characters |
|---|---|
| All 32 tool schemas | 19,215 |
| `read_rows`, full 10,000-row sheet | 2.2 to 2.5 million |
| `export_sheet_csv`, full 10,000-row sheet | 0.9 to 1.1 million |
| `get_doc` | 4,559 to 11,348 |

Sizes were measured before the quota values changed. That change does not materially affect them.

Empty container startup: about 0.25 s, measured over 5 runs at 0.23 to 0.27 s.

## Full-run estimate (540 runs)

Built by hand per category from the rows above, using list prices from the Go docs. It rests on one run per cell, and
gaps were filled by assumption: Kimi's M01 under A and B is assumed to match GLM's tokens, and Kimi's B L01 to match its A L01.

| Model | Tokens | Estimated allowance used | Assumes |
|---|---|---|---|
| glm-5.3-flash | About 90M | About $7 | About 60% cached, as measured |
| kimi-k2.7-code, as measured | About 20M | About $21 | Overflows on large data, with no caching discount |
| kimi-k2.7-code, worst case | About 90M | About $45 to $90 | Survives large data like GLM. The range is with or without caching |

- **Total: about 110M tokens and 3,200 requests in the expected case, and up to about 180M tokens in the worst case.**
- Conditions A and B are about 98% of the tokens. C is about 2M.
- Time: about 4 to 5 hours at concurrency 2, before any pauses for usage windows.
- Prices per 1M tokens: GLM $0.15 input, $0.50 output, $0.03 cached. Kimi $0.95 input, $4.00 output, $0.19 cached.

Limits on the Go plan, per model: $60 monthly, $30 weekly, $12 per 5 hours.

- GLM fits inside one 5-hour window.
- Kimi's expected $21 exceeds the 5-hour limit, so the run would pause and resume across at least two windows.
- Kimi's worst case exceeds the weekly limit and possibly the monthly one.

These dollar figures measure use of the plan's allowance, not extra charges, provided pay-as-you-go fallback is off.
