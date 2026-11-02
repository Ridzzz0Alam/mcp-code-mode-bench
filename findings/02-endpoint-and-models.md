# Opencode Go endpoint and models

Source for documentation claims: https://opencode.ai/v2/docs/console/go/, read on 2026-11-02. Limits may change, so
check again before a full run.

## Observed behaviour

- **Session header required:** without `x-opencode-session`, requests fail with HTTP 400, "Request is missing
  x-opencode-session and cannot be routed efficiently". The runner sends one stable ID per run.
- **Listing models:** `GET /models` works at the configured base URL and uses no chat tokens.
- **Oversized requests:** a request carrying about 2.3 million characters got no response in about 22 minutes across
  retries. No clean rejection was seen. The runner now gives such requests one attempt and logs `oversized_request`.
- **Region restriction:** `deepseek-v4.1-flash` needed Global regions enabled in the workspace Privacy settings. The
  human later enabled Global.
- **Allowance field:** the docs say responses report usage as `opencode.allowance`. `provider_extra` was empty in the
  cached responses inspected, so this has not been seen in practice. The field may be elsewhere in the response.

## Models

Chosen by the human: **`glm-5.3-flash` and `kimi-k2.7-code`**, after concern about token use with `kimi-k3`. Models
are only frozen once the full run starts.

| Model | Temperature 0 | Tool calls | `usage` returned | Cached token count |
|---|---|---|---|---|
| glm-5.3-flash | Accepted | Yes | Yes | Reported |
| kimi-k2.7-code | **Rejected**, runs at its default | Yes | Yes | **Not reported**, on every run so far |

Consequences:
- Compare conditions within each model. Comparing the two models directly is less clean, because only GLM is at temperature 0.
- Kimi's trials may vary more from each other.
- Cached tokens cannot be compared between the models. Total tokens can.

The spec's example pairing was one Kimi and one DeepSeek. It was offered only as an example, so this pair stays within
the spec. With Global enabled, DeepSeek may now work, but this has not been tested.

## Plan terms

- Go is $10/month, and Go Plus is $40/month.
- Limits are monthly dollar amounts per model: 20% available per 5 hours, 50% per week, 100% per month.
- On Go, both GLM-5.3-Flash and Kimi K2.7 Code have a $60 monthly limit, so $12 per 5 hours and $30 per week. On Go Plus it is $180.
- Prices per 1M tokens: GLM-5.3-Flash $0.15 input, $0.50 output, $0.03 cached read. Kimi K2.7 Code $0.95, $4.00, $0.19.
- The docs do not say when the 5-hour and weekly windows reset.
- Pay-as-you-go fallback, when enabled, keeps requests going past the limits by spending your balance. This wording came from a page summary rather than the verbatim text, so confirm it in the console.

## Is this benchmark an allowed use?

Neither the docs nor the Terms of Use explicitly allow or ban it. See
[06-usage-policy.md](06-usage-policy.md) for the clause-by-clause reading and the open questions for the human.

The runner identifies itself as `mcp-code-mode-bench/0.1`, sends a stable `x-opencode-session`, and uses one account at
concurrency 2. The residual grey area is the Terms' clauses on programmatic extraction, unattended processes, and
unreasonable load; the practical constraint is the per-model dollar allowance, not a permission rule.
