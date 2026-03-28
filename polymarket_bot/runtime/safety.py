from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable
import asyncio

from polymarket_bot.runtime.policy import ExecutionMode


STOP_REASON_SAFETY_THRESHOLD_EXCEEDED = "safety_threshold_exceeded"
STOP_REASON_LIVE_SAFETY_ABORT = "live_safety_abort"


@dataclass(frozen=True)
class RuntimeSafetyConfig:
    preflight_probe_timeout_sec: float = 1.0
    preflight_probe_max_attempts: int = 2
    adapter_order_timeout_sec: float = 2.0
    max_consecutive_adapter_failures: int = 3

    @classmethod
    def from_config(cls, cfg: dict[str, object]) -> "RuntimeSafetyConfig":
        def _as_float(value: object | None, default: float) -> float:
            if value is None:
                return default
            try:
                return float(str(value))
            except (TypeError, ValueError):
                return default

        def _as_int(value: object | None, default: int) -> int:
            if value is None:
                return default
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return default

        return cls(
            preflight_probe_timeout_sec=_as_float(cfg.get("RUNTIME_PREFLIGHT_PROBE_TIMEOUT_SEC", 1.0), 1.0),
            preflight_probe_max_attempts=_as_int(cfg.get("RUNTIME_PREFLIGHT_PROBE_MAX_ATTEMPTS", 2), 2),
            adapter_order_timeout_sec=_as_float(cfg.get("RUNTIME_ADAPTER_TIMEOUT_SEC", 2.0), 2.0),
            max_consecutive_adapter_failures=_as_int(cfg.get("RUNTIME_MAX_CONSECUTIVE_ADAPTER_FAILURES", 3), 3),
        )


async def with_timeout(timeout_sec: float, awaitable: Awaitable[Any]) -> Any:
    return await asyncio.wait_for(awaitable, timeout=timeout_sec)


@dataclass
class FailureThresholdTracker:
    mode: ExecutionMode
    max_consecutive_adapter_failures: int
    consecutive_adapter_failures: int = 0

    def on_success(self) -> None:
        self.consecutive_adapter_failures = 0

    def on_adapter_failure(self) -> str | None:
        self.consecutive_adapter_failures += 1
        if self.consecutive_adapter_failures < self.max_consecutive_adapter_failures:
            return None
        if self.mode == ExecutionMode.LIVE:
            return STOP_REASON_LIVE_SAFETY_ABORT
        return STOP_REASON_SAFETY_THRESHOLD_EXCEEDED


async def run_bounded_retries(
    *,
    operation_name: str,
    max_attempts: int,
    timeout_sec: float,
    operation: Callable[[], Awaitable[Any]],
    on_attempt: Callable[[int], None] | None = None,
) -> Any:
    if max_attempts <= 0:
        raise ValueError("max_attempts must be >= 1")

    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        if on_attempt is not None:
            on_attempt(attempt)
        try:
            return await with_timeout(timeout_sec, operation())
        except Exception:
            if attempt >= max_attempts:
                raise

    raise RuntimeError(f"{operation_name} exhausted retries")
