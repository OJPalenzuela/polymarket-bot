from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ExecutionMode(str, Enum):
    PAPER = "paper"
    SHADOW_LIVE = "shadow_live"
    LIVE = "live"


@dataclass(frozen=True)
class ExecutionPolicy:
    mode: ExecutionMode
    allow_live_order_submit: bool
    allow_live_connectivity_probe: bool
    fail_closed: bool = True


def parse_bool(value: object | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def resolve_execution_mode(*, execution_mode: object | None, paper_mode: object | None) -> ExecutionMode:
    """Resolve execution mode with strict parsing and legacy PAPER_MODE fallback.

    Precedence:
    1) explicit execution_mode
    2) legacy PAPER_MODE (true -> paper, false -> live)
    3) default paper
    """

    if execution_mode is not None:
        raw = str(execution_mode).strip().lower()
        try:
            return ExecutionMode(raw)
        except ValueError as exc:
            allowed = ", ".join(m.value for m in ExecutionMode)
            raise ValueError(f"invalid execution_mode '{execution_mode}', allowed: {allowed}") from exc

    if paper_mode is not None:
        return ExecutionMode.PAPER if parse_bool(paper_mode, default=True) else ExecutionMode.LIVE

    return ExecutionMode.PAPER


def build_execution_policy(mode: ExecutionMode) -> ExecutionPolicy:
    if mode == ExecutionMode.PAPER:
        return ExecutionPolicy(
            mode=mode,
            allow_live_order_submit=False,
            allow_live_connectivity_probe=False,
            fail_closed=True,
        )
    if mode == ExecutionMode.SHADOW_LIVE:
        return ExecutionPolicy(
            mode=mode,
            allow_live_order_submit=False,
            allow_live_connectivity_probe=True,
            fail_closed=True,
        )
    return ExecutionPolicy(
        mode=mode,
        allow_live_order_submit=True,
        allow_live_connectivity_probe=True,
        fail_closed=True,
    )
