import asyncio
import json
import datetime
from pathlib import Path

import pytest

from polymarket_bot.client import create_client
from polymarket_bot.persistence import JSONLEventStore
from polymarket_bot.runtime import RuntimeOrchestrator
from polymarket_bot.strategy import TickContext


class SequenceClock:
    def __init__(self):
        self._idx = -1
        self._base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

    def __call__(self):
        self._idx += 1
        return self._base + datetime.timedelta(seconds=self._idx)


class AlwaysIntentStrategy:
    async def on_tick(self, ctx: TickContext):
        from polymarket_bot.strategy import OrderIntent

        return OrderIntent(
            market_id=ctx.market_id,
            side="buy",
            price=0.55,
            size=1.0,
            order_type="limit",
            client_id=f"{ctx.run_id}-tick-{ctx.tick_id}",
        )


class NoopStrategy:
    async def on_tick(self, ctx: TickContext):
        return None


def _read_events(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_event_schema_envelope_fields(tmp_path):
    events_path = tmp_path / "runtime-events.jsonl"
    client = create_client(paper_mode=True)
    runtime = RuntimeOrchestrator(
        client=client,
        strategy=NoopStrategy(),
        event_store=JSONLEventStore(events_path),
        tick_seconds=0.01,
        market_id="m1",
        clock_now=SequenceClock(),
        run_id_factory=lambda: "run-schema",
    )

    asyncio.run(runtime.run(max_ticks=1))
    rows = _read_events(events_path)
    assert len(rows) > 0

    required = {"event_id", "event_type", "ts", "run_id", "tick_id", "level", "component", "payload"}
    for row in rows:
        assert required.issubset(set(row.keys()))

    event_types = {r["event_type"] for r in rows}
    assert "runtime_started" in event_types
    assert "tick_started" in event_types
    assert "strategy_decision" in event_types
    assert "tick_completed" in event_types
    assert "runtime_stopped" in event_types


def test_jsonl_store_retries_once_on_oserror(tmp_path, monkeypatch):
    path = tmp_path / "retry.jsonl"
    store = JSONLEventStore(path)

    from polymarket_bot.logging import make_event

    event = make_event(
        event_type="tick_started",
        ts="2026-01-01T00:00:00Z",
        run_id="run-1",
        tick_id=1,
        level="INFO",
        component="runtime",
        payload={},
    )

    original_open = Path.open
    calls = {"n": 0}

    def flaky_open(self, *args, **kwargs):
        if self == path and calls["n"] == 0:
            calls["n"] += 1
            raise OSError("temporary disk error")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky_open)
    asyncio.run(store.append(event))

    assert calls["n"] == 1
    rows = _read_events(path)
    assert len(rows) == 1


def test_jsonl_store_raises_after_second_oserror(tmp_path, monkeypatch):
    path = tmp_path / "retry-fail.jsonl"
    store = JSONLEventStore(path)

    from polymarket_bot.logging import make_event

    event = make_event(
        event_type="tick_started",
        ts="2026-01-01T00:00:00Z",
        run_id="run-1",
        tick_id=1,
        level="INFO",
        component="runtime",
        payload={},
    )

    original_open = Path.open

    def always_fail_open(self, *args, **kwargs):
        if self == path:
            raise OSError("permanent disk error")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", always_fail_open)
    with pytest.raises(OSError):
        asyncio.run(store.append(event))


def test_event_chain_allowed_order_includes_order_result(tmp_path):
    events_path = tmp_path / "allowed.jsonl"
    client = create_client(paper_mode=True, config={"RISK_MAX_ORDER_SIZE": "10", "RISK_MAX_POSITION": "100", "RISK_COOLDOWN_SEC": "0"})
    runtime = RuntimeOrchestrator(
        client=client,
        strategy=AlwaysIntentStrategy(),
        event_store=JSONLEventStore(events_path),
        tick_seconds=0.01,
        market_id="m1",
        clock_now=SequenceClock(),
        run_id_factory=lambda: "run-allowed",
    )

    asyncio.run(runtime.run(max_ticks=1))
    rows = _read_events(events_path)

    chain = [r["event_type"] for r in rows if r.get("tick_id") == 1]
    assert chain == ["tick_started", "strategy_decision", "order_result", "tick_completed"]

    order = next(r for r in rows if r["event_type"] == "order_result")
    assert order["payload"]["status"] == "simulated"
    assert order["payload"]["order_id"] is not None


def test_event_chain_deny_records_rejection_and_no_adapter_execution(tmp_path):
    events_path = tmp_path / "denied.jsonl"
    client = create_client(paper_mode=True, config={"RISK_MAX_ORDER_SIZE": "0.1", "RISK_MAX_POSITION": "1", "RISK_COOLDOWN_SEC": "0"})
    runtime = RuntimeOrchestrator(
        client=client,
        strategy=AlwaysIntentStrategy(),
        event_store=JSONLEventStore(events_path),
        tick_seconds=0.01,
        market_id="m1",
        clock_now=SequenceClock(),
        run_id_factory=lambda: "run-denied",
    )

    asyncio.run(runtime.run(max_ticks=1))
    rows = _read_events(events_path)

    order = next(r for r in rows if r["event_type"] == "order_result")
    assert order["payload"]["status"] == "rejected"
    assert order["payload"]["rejection_reason"] == "exceeds max_order_size"

    # No direct adapter event type exists in PR2 runtime contract.
    assert all(r["event_type"] != "adapter.executed" for r in rows)

    chain = [r["event_type"] for r in rows if r.get("tick_id") == 1]
    assert chain == ["tick_started", "strategy_decision", "order_result", "tick_completed"]


def test_lifecycle_events_present_in_bounded_run(tmp_path):
    events_path = tmp_path / "lifecycle.jsonl"
    client = create_client(paper_mode=True)
    runtime = RuntimeOrchestrator(
        client=client,
        strategy=NoopStrategy(),
        event_store=JSONLEventStore(events_path),
        tick_seconds=0.01,
        market_id="m1",
        clock_now=SequenceClock(),
        run_id_factory=lambda: "run-lifecycle",
    )

    asyncio.run(runtime.run(max_ticks=2))
    rows = _read_events(events_path)
    event_types = [r["event_type"] for r in rows]

    assert event_types[0] == "runtime_started"
    assert event_types[-1] == "runtime_stopped"
