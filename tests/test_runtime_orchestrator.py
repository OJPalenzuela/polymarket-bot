import asyncio
import datetime
import json

import pytest

from polymarket_bot.runtime import RuntimeOrchestrator
from polymarket_bot.runtime_main import _run_from_config
from polymarket_bot.runtime.policy import ExecutionMode
from polymarket_bot.runtime.safety import RuntimeSafetyConfig
from polymarket_bot.strategy import OrderIntent, TickContext


class SequenceClock:
    def __init__(self):
        self._idx = -1
        self._base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)

    def __call__(self):
        self._idx += 1
        return self._base + datetime.timedelta(seconds=self._idx)


class InMemoryStore:
    def __init__(self, *, always_fail: bool = False):
        self.events = []
        self.always_fail = always_fail

    async def append(self, event):
        if self.always_fail:
            raise OSError("disk failure")
        self.events.append(event)


class NoopStrategy:
    async def on_tick(self, ctx: TickContext):
        return None


class IntentThenNoopStrategy:
    async def on_tick(self, ctx: TickContext):
        if ctx.tick_id == 1:
            return OrderIntent(
                market_id=ctx.market_id,
                side="buy",
                price=0.51,
                size=1.0,
                order_type="limit",
                client_id=f"{ctx.run_id}-tick-1",
            )
        return None


class FailingFirstTickStrategy:
    async def on_tick(self, ctx: TickContext):
        if ctx.tick_id == 1:
            raise RuntimeError("strategy boom")
        return None


class SpyClient:
    def __init__(self):
        self.calls = []

    async def place_order_async(self, order):
        self.calls.append(order)
        return {
            "order_id": f"fake-{order['client_id']}",
            "status": "simulated",
            "filled_size": order["size"],
            "avg_price": order["price"],
            "timestamp": "2026-01-01T00:00:00Z",
            "simulated": True,
            "rejection_reason": None,
        }


class RejectingAdapterErrorClient:
    def __init__(self):
        self.calls = 0

    async def place_order_async(self, order):
        self.calls += 1
        return {
            "order_id": None,
            "status": "rejected",
            "filled_size": 0.0,
            "avg_price": None,
            "timestamp": "2026-01-01T00:00:00Z",
            "simulated": True,
            "rejection_reason": "adapter_connectivity",
            "error_type": "adapter_connectivity",
            "retry_decision": "no_blind_retry",
            "retry_count": 0,
        }


def test_clock_injection_drives_reproducible_ticks():
    store = InMemoryStore()
    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    runtime = RuntimeOrchestrator(
        client=SpyClient(),
        strategy=NoopStrategy(),
        event_store=store,
        tick_seconds=0.1,
        market_id="m1",
        clock_now=SequenceClock(),
        sleep_fn=fake_sleep,
        run_id_factory=lambda: "run-fixed",
        execution_mode=ExecutionMode.PAPER,
    )

    summary = asyncio.run(runtime.run(max_ticks=2))
    assert summary.ticks_total == 2

    tick_started = [e for e in store.events if e.event_type == "tick_started"]
    assert [e.tick_id for e in tick_started] == [1, 2]
    assert sleep_calls == [0.1]  # no extra sleep after final tick


def test_max_ticks_executes_exact_count_and_pipeline_client_only_no_action():
    store = InMemoryStore()
    spy_client = SpyClient()
    runtime = RuntimeOrchestrator(
        client=spy_client,
        strategy=IntentThenNoopStrategy(),
        event_store=store,
        tick_seconds=0.01,
        market_id="m1",
        clock_now=SequenceClock(),
        run_id_factory=lambda: "run-fixed",
        execution_mode=ExecutionMode.PAPER,
    )

    summary = asyncio.run(runtime.run(max_ticks=2))
    assert summary.ticks_total == 2
    assert len(spy_client.calls) == 1  # only first tick places through Client

    order_events = [e for e in store.events if e.event_type == "order_result"]
    assert len(order_events) == 1
    assert order_events[0].tick_id == 1

    tick_completed = [e for e in store.events if e.event_type == "tick_completed"]
    assert [e.tick_id for e in tick_completed] == [1, 2]


def test_graceful_shutdown_at_safe_boundary():
    store = InMemoryStore()
    spy_client = SpyClient()
    holder = {}

    async def fake_sleep(_seconds: float):
        holder["runtime"].request_stop("manual_stop")

    runtime = RuntimeOrchestrator(
        client=spy_client,
        strategy=NoopStrategy(),
        event_store=store,
        tick_seconds=1.0,
        market_id="m1",
        clock_now=SequenceClock(),
        sleep_fn=fake_sleep,
        run_id_factory=lambda: "run-fixed",
        execution_mode=ExecutionMode.PAPER,
    )
    holder["runtime"] = runtime

    summary = asyncio.run(runtime.run(max_ticks=10))
    assert summary.ticks_total == 1
    assert summary.stop_reason == "manual_stop"
    assert any(e.event_type == "tick_completed" and e.tick_id == 1 for e in store.events)


def test_invalid_interval_fails_fast():
    with pytest.raises(ValueError, match="interval must be positive"):
        RuntimeOrchestrator(
            client=SpyClient(),
            strategy=NoopStrategy(),
            event_store=InMemoryStore(),
            tick_seconds=0,
            market_id="m1",
        )


def test_strategy_error_continues_next_tick():
    store = InMemoryStore()
    runtime = RuntimeOrchestrator(
        client=SpyClient(),
        strategy=FailingFirstTickStrategy(),
        event_store=store,
        tick_seconds=0.01,
        market_id="m1",
        clock_now=SequenceClock(),
        run_id_factory=lambda: "run-fixed",
        execution_mode=ExecutionMode.PAPER,
    )

    summary = asyncio.run(runtime.run(max_ticks=2))
    assert summary.ticks_total == 2
    assert any(e.event_type == "runtime_error" and e.tick_id == 1 for e in store.events)
    completed = [e for e in store.events if e.event_type == "tick_completed"]
    assert [e.tick_id for e in completed] == [1, 2]


def test_persistence_failure_requests_graceful_stop():
    runtime = RuntimeOrchestrator(
        client=SpyClient(),
        strategy=NoopStrategy(),
        event_store=InMemoryStore(always_fail=True),
        tick_seconds=0.01,
        market_id="m1",
        clock_now=SequenceClock(),
        run_id_factory=lambda: "run-fixed",
        execution_mode=ExecutionMode.PAPER,
    )

    summary = asyncio.run(runtime.run(max_ticks=5))
    assert summary.stop_reason == "persistence_error"
    assert summary.ticks_total == 0


def test_runtime_main_rejects_live_without_opt_in(tmp_path, monkeypatch):
    class Args:
        paper_mode = None
        execution_mode = "live"
        live_enabled = "false"
        interval = 0.01
        max_ticks = 1
        events_path = str(tmp_path / "events.jsonl")
        market_id = None

    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="startup_failed"):
        asyncio.run(_run_from_config(Args()))

    rows = [json.loads(x) for x in (tmp_path / "events.jsonl").read_text().splitlines() if x.strip()]
    assert any(r["event_type"] == "startup_failed" for r in rows)


def test_runtime_main_runs_bounded_paper_mode(tmp_path, monkeypatch):
    class Args:
        paper_mode = "true"
        execution_mode = None
        live_enabled = None
        interval = 0.01
        max_ticks = 1
        events_path = str(tmp_path / "events.jsonl")
        market_id = "m1"

    monkeypatch.chdir(tmp_path)
    rc = asyncio.run(_run_from_config(Args()))
    assert rc == 0
    assert (tmp_path / "events.jsonl").exists()


def test_runtime_stops_on_adapter_failure_threshold_shadow_mode():
    store = InMemoryStore()
    client = RejectingAdapterErrorClient()
    runtime = RuntimeOrchestrator(
        client=client,
        strategy=IntentThenNoopStrategy(),
        event_store=store,
        tick_seconds=0.01,
        market_id="m1",
        clock_now=SequenceClock(),
        run_id_factory=lambda: "run-fixed",
        execution_mode=ExecutionMode.SHADOW_LIVE,
        safety_config=RuntimeSafetyConfig(max_consecutive_adapter_failures=1),
    )

    summary = asyncio.run(runtime.run(max_ticks=3))
    assert summary.stop_reason == "safety_threshold_exceeded"


def test_runtime_stops_fail_closed_faster_in_live_mode():
    store = InMemoryStore()
    client = RejectingAdapterErrorClient()
    runtime = RuntimeOrchestrator(
        client=client,
        strategy=IntentThenNoopStrategy(),
        event_store=store,
        tick_seconds=0.01,
        market_id="m1",
        clock_now=SequenceClock(),
        run_id_factory=lambda: "run-fixed",
        execution_mode=ExecutionMode.LIVE,
        safety_config=RuntimeSafetyConfig(max_consecutive_adapter_failures=1),
    )

    summary = asyncio.run(runtime.run(max_ticks=3))
    assert summary.stop_reason == "live_safety_abort"
