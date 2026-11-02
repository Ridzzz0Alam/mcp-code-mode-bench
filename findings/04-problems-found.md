# Problems found

Kept so that nobody reintroduces them, and because several would have invalidated results without any visible error.

## In the spec

| Problem | Effect if left alone | Fix |
|---|---|---|
| Cache key omitted the trial number | Trials 2 and 3 would replay trial 1, showing false zero variance | `trial` added to the key |
| Shared mock state with concurrency 2 | Parallel runs would corrupt each other | Each run gets its own CRM state |
| API-call ban conflicted with fetching model IDs | Could not follow both rules | `--list-models`, approved by the human |

## In the build

| Milestone | Problem | How it surfaced | Fix |
|---|---|---|---|
| M0 | `.gitignore` plan would have ignored `data/generate.py` | Reviewing the plan | Ignore generated data only |
| M1 | A test assertion could never fail | Reviewing the tests | Removed |
| M2 | **L12 answer was 50 of 50 reps**, so it could be guessed | Reading the computed answers, not from a failing test | Raised quotas (answer now 28), and added a test against extreme counts |
| M2 | Oracle's `name` parameter clashed with `create_contact(name=...)` | Test crash | Positional-only parameter |
| M3 | Error detail was discarded on API failure | First dry run | Reported on stderr with the key redacted |
| M3 | Failed dry-run rows counted as finished | First dry run | Dry runs retry `api_error` rows |
| M3 | `git_commit` logged the literal text `HEAD` with no commits | Reading `run_meta.json` | Check the return code |
| M3 | Oversized requests retried for 5 minutes each | kimi-k3 dry run and M3_FEEDBACK.md | One attempt, then `oversized_request` |
| M4 | Base image tag was unpinned | Review | Pinned by digest |
| M4 | Async test fixture crossed tasks and broke the MCP client | Test errors | One task owns the client's lifetime |

## Not yet fixed

- `results/run_meta.json` is overwritten by every invocation, and `temperature_dropped_for` covers only the current
  process. Fix before M6.
- The runner's printed dry-run extrapolation assumes every task resembles the one that ran. Use a per-category estimate.

## Security incident

The real API key was pasted into `.env.example`, which git does not ignore. It was caught before any commit and removed
by the human, and a scan found no key-like strings outside `.env`. It had already been displayed in a session's
context, so replacing it was recommended. Whether that has happened has not been confirmed.
