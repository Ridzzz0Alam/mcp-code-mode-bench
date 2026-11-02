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

**Rejected: an OpenAI API key.** The human ruled this out on 2026-11-02.
