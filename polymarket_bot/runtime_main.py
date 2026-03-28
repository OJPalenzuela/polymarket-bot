from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from polymarket_bot.client import create_client
from polymarket_bot.config import load_config
from polymarket_bot.persistence import JSONLEventStore
from polymarket_bot.runtime import RuntimeOrchestrator
from polymarket_bot.strategy import DeterministicStrategy


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PR2 bounded runtime in paper mode.")
    parser.add_argument("--paper-mode", dest="paper_mode", default=None, help="true|false (PR2 supports true only)")
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

    paper_mode = _bool_like(args.paper_mode if args.paper_mode is not None else cfg.get("PAPER_MODE"), default=True)
    if not paper_mode:
        raise ValueError("live mode is out of scope for PR2; use paper_mode=true")

    interval = float(args.interval if args.interval is not None else cfg.get("RUNTIME_TICK_SECONDS", 1.0))
    if interval <= 0:
        raise ValueError("interval must be positive")

    max_ticks_val = args.max_ticks if args.max_ticks is not None else cfg.get("RUNTIME_MAX_TICKS", 3)
    max_ticks = int(max_ticks_val) if max_ticks_val is not None else None
    if max_ticks is not None and max_ticks <= 0:
        raise ValueError("max_ticks must be > 0")

    events_path = args.events_path or cfg.get("RUNTIME_EVENTS_PATH") or "runtime-events.jsonl"
    market_id = args.market_id or cfg.get("RUNTIME_MARKET_ID") or "default-market"

    client = create_client(paper_mode=True, config=cfg)
    strategy = DeterministicStrategy()
    store = JSONLEventStore(Path(str(events_path)))

    runtime = RuntimeOrchestrator(
        client=client,
        strategy=strategy,
        event_store=store,
        tick_seconds=interval,
        market_id=str(market_id),
    )
    await runtime.run(max_ticks=max_ticks)
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run_from_config(args))


if __name__ == "__main__":
    raise SystemExit(main())
