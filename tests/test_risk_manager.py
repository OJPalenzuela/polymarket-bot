import asyncio
from decimal import Decimal

from polymarket_bot.risk import RiskManager


class TimeController:
    def __init__(self, start: float = 0.0):
        self._t = start

    def time(self):
        return self._t

    def advance(self, s: float):
        self._t += s


def test_risk_manager_rejects_large_order(monkeypatch):
    rm = RiskManager(max_position_size=100, max_order_size=5, cooldown_seconds=1)
    allowed, reason = asyncio.run(rm.can_open_position("m1", Decimal("6")))
    assert not allowed
    assert reason == "exceeds max_order_size"


def test_risk_manager_applies_cooldown(monkeypatch):
    tc = TimeController(start=0)
    monkeypatch.setattr("time.time", tc.time)
    rm = RiskManager(max_position_size=100, max_order_size=10, cooldown_seconds=60)
    # simulate a committed order at t=0
    asyncio.run(rm.commit_open_position("m1", Decimal("1")))
    # at t=0, last_order_ts set, advance to t=30
    tc.advance(30)
    allowed, reason = asyncio.run(rm.can_open_position("m1", Decimal("1")))
    assert not allowed
    assert reason == "cooldown"


def test_risk_manager_allows_after_cooldown(monkeypatch):
    tc = TimeController(start=0)
    monkeypatch.setattr("time.time", tc.time)
    rm = RiskManager(max_position_size=100, max_order_size=10, cooldown_seconds=60)
    asyncio.run(rm.commit_open_position("m1", Decimal("1")))
    tc.advance(61)
    allowed, reason = asyncio.run(rm.can_open_position("m1", Decimal("1")))
    assert allowed and reason is None


def test_risk_manager_rejects_if_max_position_reached(monkeypatch):
    rm = RiskManager(max_position_size=100, max_order_size=10, cooldown_seconds=0)
    # set existing position to max
    asyncio.run(rm.commit_open_position("m1", Decimal("100")))
    allowed, reason = asyncio.run(rm.can_open_position("m1", Decimal("1")))
    assert not allowed
    assert reason == "max_position_size_reached"


def test_risk_manager_trigger_kill_switch_and_blocks(monkeypatch):
    tc = TimeController(start=0)
    monkeypatch.setattr("time.time", tc.time)
    rm = RiskManager(max_position_size=100, max_order_size=10, cooldown_seconds=0, pnl_limit=Decimal("10"))
    # apply negative pnl to exceed limit
    asyncio.run(rm.update_pnl(Decimal("-11")))
    allowed, reason = asyncio.run(rm.can_open_position("m1", Decimal("1")))
    assert not allowed
    assert "KILL_SWITCH" in reason
