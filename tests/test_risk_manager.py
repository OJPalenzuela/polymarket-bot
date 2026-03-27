import asyncio
import time
from decimal import Decimal

import pytest

from polymarket_bot.risk import RiskManager


class TimeController:
    def __init__(self, start: float = 0.0):
        self._t = start

    def time(self):
        return self._t

    def advance(self, s: float):
        self._t += s


@pytest.mark.asyncio
async def test_risk_manager_rejects_large_order(monkeypatch):
    rm = RiskManager(max_position_size=100, max_order_size=5, cooldown_seconds=1)
    allowed, reason = await rm.can_open_position("m1", Decimal("6"))
    assert not allowed
    assert reason == "exceeds max_order_size"


@pytest.mark.asyncio
async def test_risk_manager_applies_cooldown(monkeypatch):
    tc = TimeController(start=0)
    monkeypatch.setattr("time.time", tc.time)
    rm = RiskManager(max_position_size=100, max_order_size=10, cooldown_seconds=60)
    # simulate a committed order at t=0
    await rm.commit_open_position("m1", Decimal("1"))
    # at t=0, last_order_ts set, advance to t=30
    tc.advance(30)
    allowed, reason = await rm.can_open_position("m1", Decimal("1"))
    assert not allowed
    assert reason == "cooldown"


@pytest.mark.asyncio
async def test_risk_manager_allows_after_cooldown(monkeypatch):
    tc = TimeController(start=0)
    monkeypatch.setattr("time.time", tc.time)
    rm = RiskManager(max_position_size=100, max_order_size=10, cooldown_seconds=60)
    await rm.commit_open_position("m1", Decimal("1"))
    tc.advance(61)
    allowed, reason = await rm.can_open_position("m1", Decimal("1"))
    assert allowed and reason is None


@pytest.mark.asyncio
async def test_risk_manager_rejects_if_max_position_reached(monkeypatch):
    rm = RiskManager(max_position_size=100, max_order_size=10, cooldown_seconds=0)
    # set existing position to max
    await rm.commit_open_position("m1", Decimal("100"))
    allowed, reason = await rm.can_open_position("m1", Decimal("1"))
    assert not allowed
    assert reason == "max_position_size_reached"


@pytest.mark.asyncio
async def test_risk_manager_trigger_kill_switch_and_blocks(monkeypatch):
    tc = TimeController(start=0)
    monkeypatch.setattr("time.time", tc.time)
    rm = RiskManager(max_position_size=100, max_order_size=10, cooldown_seconds=0, pnl_limit=Decimal("10"))
    # apply negative pnl to exceed limit
    await rm.update_pnl(Decimal("-11"))
    allowed, reason = await rm.can_open_position("m1", Decimal("1"))
    assert not allowed
    assert "KILL_SWITCH" in reason
