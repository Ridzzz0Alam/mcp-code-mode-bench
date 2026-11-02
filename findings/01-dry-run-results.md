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

## Rough cost estimate

Estimated by hand, per category, from the runs above:

| Condition | Estimated total tokens | Basis |
|---|---|---|
| A | About 90 million | 12 large-data tasks at 1.2M, plus the smaller tasks, across 2 models and 3 trials |
| C | About 2 to 3 million | 12 tasks at about 12K, 10 at about 16K, and a guess for simple tasks, across 2 models and 3 trials |
| B | Unknown | Not built yet |

- The A figure uses GLM only. A model that reads whole sheets would change it a lot.
- No simple task has run under C, so that part of the estimate is a guess.
- About 65% of input tokens on GLM's L01 were cached, so billed usage should be lower than the raw count.
- No dollar figure exists yet, because GLM and Kimi prices have not been recorded.
- The per-task extrapolations printed by `runner.py` (for example 217M input tokens from L01) assume every task looks
  like that one. Do not quote them as estimates of the full run.
