# Is this benchmark an allowed use of Opencode Go?

Sources, both read on 2026-11-02:

- Go docs: https://opencode.ai/v2/docs/console/go/
- Terms of Use, effective 2026-08-15: https://opencode.ai/legal/terms-of-service

This is a reading of the published terms, not legal advice. OpenCode has "the sole right to decide whether you are in
violation of any of the restrictions".

## Short answer

Neither document explicitly allows nor bans running a benchmark. The Go docs define the intended client as a coding
agent sending typical agent traffic, and say traffic is monitored for abuse. The Terms of Use add general
restrictions that a single-account, modest-concurrency, synthetic-data benchmark can satisfy, but clauses about
programmatic extraction, unattended processes, and unreasonable load are broad enough to be a real grey area. In
practice the binding constraint is the plan's dollar allowance, not a permission rule.

## What the Go docs say

- Go "is designed for OpenCode and other coding agents that produce similar types of requests."
- "Traffic is monitored for abuse that degrades the experience for other users."
- Clients should:
  1. send typical coding agent traffic;
  2. identify themselves with their own user agent, such as `my-coding-agent/1.0`, not a generic SDK or HTTP library
     name;
  3. send a stable session ID in `x-opencode-session` per conversation, so routing and prompt caching work.

There is no mention of benchmarks or evaluation anywhere on the page.

## Relevant Terms of Use clauses

The Terms require use "for your own internal use, and not on behalf of or for the benefit of any third party." The
restrictions section then prohibits using the Services in a manner that:

| # | Clause (abridged) | Read against this project |
|---|---|---|
| 4 | creates or uses accounts in bulk, or multiple accounts to circumvent usage limits or billing obligations | One workspace only. Do not open accounts to get around $60/model caps. |
| 5 | automatically or programmatically extracts data or Output | Grey area on its face: the harness receives and stores model Output. The clause appears aimed at bulk extraction of service Content, and an API client necessarily receives Output programmatically, but the wording is broad. |
| 10 | runs processes activated while you are not logged in, or that otherwise interfere with the proper working of the Services, including by placing an unreasonable load on the infrastructure | A 4-5 hour unattended batch is the main risk. Concurrency 2 is modest, and the plan limits cap spend, but an overnight run while away is closer to the literal text. |
| 11 | crawls, scrapes, or spiders any page, data, or portion of the Services | Not applicable: the harness calls the chat API as an agent, it does not crawl the site or console. |
| 12 | copies or stores any significant portion of the Content | Storing 540 of your own run outputs for analysis is normal agent behaviour, but "significant portion" is undefined. |
| 7 | uses Output to develop AI models that compete with the Services | Not applicable: no model training. |
| 6 | represents that Output was human-generated when it was not | Label all published examples and outputs as model-generated. |

The Terms also prohibit scraping and reverse engineering, and require that Content not infringe rights. None of that is
at issue here: tasks and data are synthetic.

## How the harness maps to the documented client requirements

| Requirement | Status |
|---|---|
| Own user agent | Yes: `mcp-code-mode-bench/0.1` (`runner.py:39`) |
| Stable session ID per conversation | Yes: UUID5 of model/condition/task/trial (`runner.py:85`), sent as `x-opencode-session` (`llm.py:134-135`) |
| Typical coding agent traffic | Yes in shape: the three agents run the same tool-calling loop against chat completions. The large-data tasks are unusually big requests, which is what the experiment measures. |
| Single account, no limit circumvention | Required operationally. Use the console's Extra Usage rather than a second account if more allowance is needed, and only with human approval. |
| No unreasonable load | Concurrency 2, bounded batches, no retry storm (`max_retries=0`). Pause at the 5-hour and weekly caps instead of forcing through. |
| Supervised processes | Prefer a supervised run or a bounded batch per invocation. Do not leave 540 runs going unattended overnight without an explicit decision. |

## Limits are the practical constraint

From [01-dry-run-results.md](01-dry-run-results.md), the full run is about 110M tokens expected (up to 180M) and about
$28 expected allowance use, with Kimi's worst case at $45 to $90. On the Go plan each model has a $60 monthly, $30
weekly, and $12 per-5-hour allowance.

- GLM's expected use fits one 5-hour window.
- Kimi's expected use exceeds the 5-hour window and needs at least two windows.
- Kimi's worst case exceeds the weekly limit and may exceed the monthly one.

If pay-as-you-go fallback is on, the run will keep spending real balance after those caps instead of pausing. Confirm
the setting before a full run, and do not enable it without cost approval.

## Decisions (2026-11-02)

- Workspace is on **Go ($10/month)**, so each model has a $60 monthly, $30 weekly, and $12 per-5-hour allowance.
- **Pay-as-you-go fallback is off**, so runs pause at the caps instead of spending balance.
- **No run yet:** the human chose to wait. The next run still needs explicit approval, and should be a supervised
  batch (`--max-requests`) rather than an unattended overnight job.

Policy position: allowed in spirit for a single-account research benchmark, with the extraction/load clauses as the
residual risk to keep visible.
