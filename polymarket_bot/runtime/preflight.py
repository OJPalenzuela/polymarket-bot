from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from polymarket_bot.adapters.base import ExchangeAdapter
from polymarket_bot.adapters.errors import AdapterError
from polymarket_bot.runtime.policy import ExecutionMode, ExecutionPolicy, parse_bool
from polymarket_bot.runtime.safety import RuntimeSafetyConfig, run_bounded_retries


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    mode: str
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    reason_class: str | None = None


def _missing_required_keys(cfg: dict[str, Any], keys: list[str]) -> list[str]:
    missing: list[str] = []
    for key in keys:
        value = cfg.get(key)
        if value is None or str(value).strip() == "":
            missing.append(key)
    return missing


async def run_preflight(
    *,
    cfg: dict[str, Any],
    policy: ExecutionPolicy,
    adapter: ExchangeAdapter,
    safety: RuntimeSafetyConfig,
) -> PreflightResult:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    if policy.mode == ExecutionMode.PAPER:
        checks_passed.append("paper_mode_no_live_secrets_required")
        return PreflightResult(ok=True, mode=policy.mode.value, checks_passed=checks_passed)

    missing = _missing_required_keys(cfg, ["ADAPTER_KIND", "ADAPTER_API_KEY", "ADAPTER_API_SECRET"])
    if missing:
        checks_failed.append(f"missing_required_config:{','.join(missing)}")
        return PreflightResult(
            ok=False,
            mode=policy.mode.value,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            reason_class="preflight_config",
        )
    checks_passed.append("required_live_config_present")

    if policy.mode == ExecutionMode.LIVE and not parse_bool(cfg.get("LIVE_ENABLED"), default=False):
        checks_failed.append("live_opt_in_required")
        return PreflightResult(
            ok=False,
            mode=policy.mode.value,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            reason_class="preflight_opt_in",
        )
    if policy.mode == ExecutionMode.LIVE:
        checks_passed.append("live_opt_in_enabled")

    probe_enabled = parse_bool(cfg.get("RUNTIME_PREFLIGHT_PROBE"), default=True)
    if not probe_enabled:
        checks_passed.append("probe_skipped_by_config")
        return PreflightResult(ok=True, mode=policy.mode.value, checks_passed=checks_passed)

    if not policy.allow_live_connectivity_probe:
        checks_failed.append("probe_disallowed_by_policy")
        return PreflightResult(
            ok=False,
            mode=policy.mode.value,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            reason_class="preflight_policy",
        )

    if not adapter.supports_connectivity_probe:
        checks_failed.append("adapter_probe_not_supported")
        return PreflightResult(
            ok=False,
            mode=policy.mode.value,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            reason_class="preflight_adapter_capability",
        )

    probe_attempts: list[int] = []
    try:
        await run_bounded_retries(
            operation_name="preflight_probe",
            max_attempts=safety.preflight_probe_max_attempts,
            timeout_sec=safety.preflight_probe_timeout_sec,
            operation=adapter.probe_connectivity,
            on_attempt=probe_attempts.append,
        )
        checks_passed.append("connectivity_probe_ok")
        checks_passed.append(f"connectivity_probe_attempts:{len(probe_attempts)}")
    except (AdapterError, TimeoutError, Exception) as exc:
        checks_failed.append(f"connectivity_probe_failed:{type(exc).__name__}")
        checks_failed.append(f"connectivity_probe_attempts:{len(probe_attempts)}")
        return PreflightResult(
            ok=False,
            mode=policy.mode.value,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            reason_class="preflight_connectivity",
        )

    return PreflightResult(ok=True, mode=policy.mode.value, checks_passed=checks_passed)
