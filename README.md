# polymarket-bot

PR3 introduces a safety-first live-adapter hardening slice while preserving PR2 deterministic paper behavior by default.

## PR3 execution policy

- Supported execution modes: `paper | shadow_live | live`
- Safe default: `paper`
- `shadow_live` is read-only (order placement suppressed)
- `live` requires explicit opt-in via `LIVE_ENABLED=true`

Backward compatibility:
- Legacy `PAPER_MODE=true|false` still works.
- If `EXECUTION_MODE` is provided, it takes precedence over `PAPER_MODE`.

## PR3 preflight and runtime safety

- Startup preflight is fail-closed for `shadow_live` and `live`.
- Required live/shadow keys: `ADAPTER_KIND`, `ADAPTER_API_KEY`, `ADAPTER_API_SECRET`.
- Optional connectivity probe is bounded by timeout + retry attempts.
- Runtime order path keeps `max_attempts=1` (no blind automatic order retries).
- Runtime stops gracefully on repeated adapter failures with classified stop reasons.

## CI gates (PR3)

Required merge gates:
- `pytest`
- `ruff check .`

Informational (non-blocking in PR3):
- `mypy polymarket_bot`

Rationale: PR3 is scoped to adapter/runtime/CI hardening with minimal blast radius; type-check is surfaced early but not mandatory until a dedicated type-debt follow-up.

## Out of scope in PR3

- Full production live infra hardening (advanced retry engines, venue-specific circuit breaking)
- Multi-market/multi-strategy orchestration changes
- Mandatory type-check gate
