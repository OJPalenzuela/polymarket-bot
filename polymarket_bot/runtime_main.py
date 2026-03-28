from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from polymarket_bot.client import create_client
from polymarket_bot.config import load_config
from polymarket_bot.logging.events import make_event
from polymarket_bot.persistence import JSONLEventStore
from polymarket_bot.runtime import RuntimeOrchestrator
from polymarket_bot.runtime.clock import utc_iso, default_clock_now
from polymarket_bot.runtime.policy import build_execution_policy, resolve_execution_mode
from polymarket_bot.runtime.preflight import run_preflight
from polymarket_bot.runtime.safety import RuntimeSafetyConfig
from polymarket_bot.strategy import DeterministicStrategy


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded runtime with PR3 execution guardrails.")
    parser.add_argument("--paper-mode", dest="paper_mode", default=None, help="legacy true|false fallback")
    parser.add_argument("--execution-mode", dest="execution_mode", default=None, help="paper|shadow_live|live")
    parser.add_argument("--live-enabled", dest="live_enabled", default=None, help="true required for live")
    parser.add_argument("--interval", dest="interval", type=float, default=None, help="Tick interval seconds (>0)")
    parser.add_argument("--max-ticks", dest="max_ticks", type=int, default=None, help="Bounded ticks (>0)")
    parser.add_argument("--events-path", dest="events_path", default=None, help="JSONL output path")
    parser.add_argument("--market-id", dest="market_id", default=None, help="Market identifier")
    return parser.parse_args()


def _bool_like(value: object | None, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


async def _run_from_config(args: argparse.Namespace) -> int:
    cfg = load_config()
    if args.execution_mode is not None:
        cfg["EXECUTION_MODE"] = args.execution_mode
    if args.paper_mode is not None:
        cfg["PAPER_MODE"] = _bool_like(args.paper_mode, default=True)
    if args.live_enabled is not None:
        cfg["LIVE_ENABLED"] = _bool_like(args.live_enabled, default=False)

    mode = resolve_execution_mode(execution_mode=cfg.get("EXECUTION_MODE"), paper_mode=cfg.get("PAPER_MODE"))
    policy = build_execution_policy(mode)
    cfg["EXECUTION_MODE"] = mode.value
    cfg["PAPER_MODE"] = mode.value == "paper"

    def _as_float(value: object | None, default: float) -> float:
        if value is None:
            return default
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return default

    def _as_int(value: object | None, default: int | None) -> int | None:
        if value is None:
            return default
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return default

    interval = _as_float(args.interval if args.interval is not None else cfg.get("RUNTIME_TICK_SECONDS", 1.0), 1.0)
    if interval <= 0:
        raise ValueError("interval must be positive")

    max_ticks_val = args.max_ticks if args.max_ticks is not None else cfg.get("RUNTIME_MAX_TICKS", 3)
    max_ticks = _as_int(max_ticks_val, None)
    if max_ticks is not None and max_ticks <= 0:
        raise ValueError("max_ticks must be > 0")

    events_path = args.events_path or cfg.get("RUNTIME_EVENTS_PATH") or "runtime-events.jsonl"
    market_id = args.market_id or cfg.get("RUNTIME_MARKET_ID") or "default-market"

    store = JSONLEventStore(Path(str(events_path)))

    client = create_client(paper_mode=(mode.value == "paper"), config=cfg)
    safety = RuntimeSafetyConfig.from_config(cfg)
    preflight = await run_preflight(cfg=cfg, policy=policy, adapter=client.adapter, safety=safety)
    if not preflight.ok:
        event = make_event(
            event_type="startup_failed",
            ts=utc_iso(default_clock_now()),
            run_id="startup",
            tick_id=None,
            level="ERROR",
            component="runtime",
            payload={
                "mode": mode.value,
                "reason_class": preflight.reason_class,
                "checks_failed": preflight.checks_failed,
            },
        )
        await store.append(event)
        raise ValueError(f"startup_failed: {preflight.reason_class}")

    strategy = DeterministicStrategy()

    runtime = RuntimeOrchestrator(
        client=client,
        strategy=strategy,
        event_store=store,
        tick_seconds=interval,
        market_id=str(market_id),
        execution_mode=mode,
        safety_config=safety,
    )
    await runtime.run(max_ticks=max_ticks)
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run_from_config(args))


if __name__ == "__main__":
    raise SystemExit(main())
