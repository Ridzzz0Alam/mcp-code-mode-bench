# Cost options

All figures are rough estimates from single dry runs, per [01-dry-run-results.md](01-dry-run-results.md). No option has
been approved yet.

## Where the tokens go

Conditions A and B on the 12 large-data tasks are 144 of the 540 runs but about 98% of the tokens. Those are the runs to
cut if cost matters.

## Options on the Opencode Go plan

Dollar figures are plan allowance, not extra charges, provided pay-as-you-go fallback is off. The real cost stays at the
$10 plan fee.

| Option | Runs | Tokens | Allowance | What is given up |
|---|---|---|---|---|
| Full spec | 540 | About 110M, up to 180M | About $28, or $50 to $100 in the worst case | Nothing |
| 4 large-data tasks instead of 12 in A and B | 444 | About 40M | About $12 | Large-data comparison rests on 4 tasks. A labelled spec change |
| GLM only, 3 trials | 270 | About 90M | About $7 | No second model |
| **GLM only, 1 trial (pilot, recommended)** | 90 | About 30M | **About $2.50** | No trial-to-trial variance until more are added |

Why the pilot is recommended:

- Its rows count as trial 1, so nothing is wasted if the run continues.
- It covers every task and condition, so it reveals whether the checks are too strict.
- It replaces single-run guesses with a measured per-task estimate.

One trial on one model cannot support firm conclusions, so the pilot alone does not complete the spec.

**Rejected: a token cap per run.** It would hide how much condition A really uses, which is what is being measured.

## Using an OpenAI key instead

The human asked what this would cost. Prices are from https://developers.openai.com/api/docs/pricing, read on
2026-11-02. Costs assume about 35M uncached input, 55M cached input, and 1.2M output per model at 3 trials, based on GLM.

| Model | Input / cached / output, per 1M | Pilot, 90 runs | 3 trials, 270 runs |
|---|---|---|---|
| `gpt-5-nano` | $0.05 / $0.005 / $0.40 | About $1 | About $2.50 |
| `gpt-6-luna` | $0.10 / $0.01 / $0.50 | About $2 to $3 | About $5 to $9 |
| `gpt-5.4-mini` | $0.75 / $0.075 / $4.50 | About $12 | About $36 |
| `gpt-6.1-sol` | $2.00 / $0.10 / $10.00 | About $30 to $60 | About $90 to $175 |
| `gpt-5.5` | $5.00 / $0.50 / $30.00 | About $80 to $160 | About $240 to $480 |

- The full 540 runs need two models, so add two rows. `gpt-6-luna` + `gpt-5-nano` is about $8 to $12.
- Ranges reflect long-context rates, which double input prices above 272K tokens. Some L01 turns reached 414K. Prices
  collected for `gpt-5-nano` and `gpt-5.4-mini` showed no long-context rate.
- Other models may behave differently from GLM, so the real bill could be well above these figures.
- Without caching, `gpt-6-luna` would cost about $10 and `gpt-6.1-sol` about $190 for 270 runs. Cache write prices appear
  on the page without explanation and are not included.
- Tool calling on these models and runner compatibility are untested. The pricing page does not list tool support.

Tradeoffs:

- An API key removes the question of whether the Go plan allows this use, but every token is billed.
- `gpt-6-luna` also appears in the Go model list, so it might be usable without a key. This is untested.
- If a key is used, the human should put it in `.env` directly and set a hard spending limit first, about $15 for a pilot.
