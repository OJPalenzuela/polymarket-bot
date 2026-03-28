from __future__ import annotations

import logging
import signal
import uuid
from dataclasses import dataclass
from typing import Optional, Callable

from polymarket_bot.client import Client
from polymarket_bot.logging.events import make_event, RuntimeEvent
from polymarket_bot.persistence import EventStore
from polymarket_bot.runtime.clock import ClockNow, SleepFn, default_clock_now, default_sleep, utc_iso
from polymarket_bot.runtime.policy import ExecutionMode
from polymarket_bot.runtime.safety import (
    FailureThresholdTracker,
    RuntimeSafetyConfig,
)
from polymarket_bot.strategy import Strategy, TickContext


@dataclass
class RuntimeSummary:
    ticks_total: int
    orders_attempted: int
    orders_rejected: int
    orders_submitted: int
    started_at: str
    stopped_at: str
    stop_reason: str


class RuntimeOrchestrator:
    def __init__(
        self,
        *,
        client: Client,
        strategy: Strategy,
        event_store: EventStore,
        tick_seconds: float,
        market_id: str,
        clock_now: ClockNow = default_clock_now,
        sleep_fn: SleepFn = default_sleep,
        logger: Optional[logging.Logger] = None,
        run_id_factory: Optional[Callable[[], str]] = None,
        execution_mode: ExecutionMode = ExecutionMode.PAPER,
        safety_config: RuntimeSafetyConfig | None = None,
    ) -> None:
        self.client = client
        self.strategy = strategy
        self.event_store = event_store
        self.tick_seconds = float(tick_seconds)
        self.market_id = market_id
        self.clock_now = clock_now
        self.sleep_fn = sleep_fn
        self.logger = logger or logging.getLogger("polymarket_bot.runtime")
        self.run_id_factory = run_id_factory or (lambda: str(uuid.uuid4()))
        self.execution_mode = execution_mode
        self.safety_config = safety_config or RuntimeSafetyConfig()
        self.failure_tracker = FailureThresholdTracker(
            mode=self.execution_mode,
            max_consecutive_adapter_failures=self.safety_config.max_consecutive_adapter_failures,
        )
        self._stop_requested = False
        self._stop_reason = "completed"

        if self.tick_seconds <= 0:
            raise ValueError("interval must be positive")

    def request_stop(self, reason: str) -> None:
        self._stop_requested = True
        self._stop_reason = reason or "requested"

    async def _emit(self, event: RuntimeEvent) -> None:
        # Log structured payload as dict, then persist.
        level = getattr(logging, event.level.upper(), logging.INFO)
        self.logger.log(level, "runtime_event", extra={"event": event.to_dict()})
        try:
            await self.event_store.append(event)
        except OSError as exc:
            # Persistence failure is critical per PR2 policy.
            if event.event_type != "runtime_error":
                err = make_event(
                    event_type="runtime_error",
                    ts=utc_iso(self.clock_now()),
                    run_id=event.run_id,
                    tick_id=event.tick_id,
                    level="ERROR",
                    component="persistence",
                    payload={"error": str(exc)},
                )
                try:
                    await self.event_store.append(err)
                except OSError:
                    pass
            self.request_stop("persistence_error")

    async def run(self, *, max_ticks: int | None = None) -> RuntimeSummary:
        if max_ticks is not None and max_ticks <= 0:
            raise ValueError("max_ticks must be > 0")

        run_id = self.run_id_factory()
        started_at = utc_iso(self.clock_now())
        ticks_total = 0
        orders_attempted = 0
        orders_rejected = 0
        orders_submitted = 0

        # best-effort signal handling (only in main thread contexts)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: self.request_stop("signal"))
            except Exception:
                pass

        await self._emit(
            make_event(
                event_type="runtime_started",
                ts=started_at,
                run_id=run_id,
                tick_id=None,
                level="INFO",
                component="runtime",
                payload={
                    "tick_seconds": self.tick_seconds,
                    "max_ticks": max_ticks,
                    "market_id": self.market_id,
                    "mode": self.execution_mode.value,
                },
            )
        )

        tick_id = 0
        while not self._stop_requested:
            if max_ticks is not None and ticks_total >= max_ticks:
                self.request_stop("max_ticks_reached")
                break

            tick_id += 1
            tick_ts = utc_iso(self.clock_now())
            await self._emit(
                make_event(
                    event_type="tick_started",
                    ts=tick_ts,
                    run_id=run_id,
                    tick_id=tick_id,
                    level="INFO",
                    component="runtime",
                    payload={"market_id": self.market_id},
                )
            )

            status = "ok"
            error_stage = None
            try:
                ctx = TickContext(run_id=run_id, tick_id=tick_id, tick_ts=tick_ts, market_id=self.market_id)
                intent = await self.strategy.on_tick(ctx)
                await self._emit(
                    make_event(
                        event_type="strategy_decision",
                        ts=utc_iso(self.clock_now()),
                        run_id=run_id,
                        tick_id=tick_id,
                        level="INFO",
                        component="strategy",
                        payload={"decision": "order_intent" if intent is not None else "noop"},
                    )
                )

                if intent is not None:
                    orders_attempted += 1
                    result = await self.client.place_order_async(intent.to_order_dict())
                    result_status = result.get("status", "unknown")
                    if result_status == "rejected":
                        orders_rejected += 1
                        error_type = str(result.get("error_type") or "")
                        if error_type.startswith("adapter_"):
                            stop_reason = self.failure_tracker.on_adapter_failure()
                            if stop_reason:
                                self.request_stop(stop_reason)
                    elif result_status == "simulated":
                        orders_submitted += 1
                        self.failure_tracker.on_success()
                    elif result_status == "submitted":
                        orders_submitted += 1
                        self.failure_tracker.on_success()

                    await self._emit(
                        make_event(
                            event_type="order_result",
                            ts=utc_iso(self.clock_now()),
                            run_id=run_id,
                            tick_id=tick_id,
                            level="INFO" if result_status != "rejected" else "WARNING",
                            component="client",
                            payload={
                                "status": result_status,
                                "order_id": result.get("order_id"),
                                "market_id": intent.market_id,
                                "side": intent.side,
                                "price": intent.price,
                                "size": intent.size,
                                "rejection_reason": result.get("rejection_reason"),
                                "error_type": result.get("error_type"),
                                "stage": result.get("stage"),
                                "retry_decision": result.get("retry_decision"),
                                "retry_count": result.get("retry_count"),
                            },
                        )
                    )

            except Exception as exc:
                status = "error"
                error_stage = "strategy_or_order"
                stop_reason = self.failure_tracker.on_adapter_failure()
                if stop_reason:
                    self.request_stop(stop_reason)
                await self._emit(
                    make_event(
                        event_type="runtime_error",
                        ts=utc_iso(self.clock_now()),
                        run_id=run_id,
                        tick_id=tick_id,
                        level="ERROR",
                        component="runtime",
                        payload={"stage": error_stage, "error": str(exc)},
                    )
                )
                # default policy: continue on strategy/order errors

            await self._emit(
                make_event(
                    event_type="tick_completed",
                    ts=utc_iso(self.clock_now()),
                    run_id=run_id,
                    tick_id=tick_id,
                    level="INFO",
                    component="runtime",
                    payload={"status": status, "error_stage": error_stage},
                )
            )

            ticks_total += 1

            if self._stop_requested:
                break
            if max_ticks is not None and ticks_total >= max_ticks:
                self.request_stop("max_ticks_reached")
                break

            await self.sleep_fn(self.tick_seconds)

        stopped_at = utc_iso(self.clock_now())
        await self._emit(
            make_event(
                event_type="runtime_stopped",
                ts=stopped_at,
                run_id=run_id,
                tick_id=None,
                level="INFO",
                component="runtime",
                payload={
                    "stop_reason": self._stop_reason,
                    "ticks_total": ticks_total,
                    "orders_attempted": orders_attempted,
                    "orders_rejected": orders_rejected,
                    "orders_submitted": orders_submitted,
                },
            )
        )

        return RuntimeSummary(
            ticks_total=ticks_total,
            orders_attempted=orders_attempted,
            orders_rejected=orders_rejected,
            orders_submitted=orders_submitted,
            started_at=started_at,
            stopped_at=stopped_at,
            stop_reason=self._stop_reason,
        )
