from __future__ import annotations

import time
import asyncio
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple, Dict


class RiskManager:
    def __init__(
        self,
        max_position_size: Decimal | float,
        max_order_size: Decimal | float,
        cooldown_seconds: int,
        pnl_limit: Optional[Decimal | float] = None,
    ) -> None:
        try:
            self.max_position_size_val = Decimal(str(max_position_size))
            self.max_order_size_val = Decimal(str(max_order_size))
        except (InvalidOperation, TypeError):
            raise ValueError("max_position_size and max_order_size must be numeric")

        if self.max_position_size_val <= 0 or self.max_order_size_val <= 0:
            raise ValueError("max sizes must be > 0")

        if cooldown_seconds is None or cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")

        self.cooldown_seconds = int(cooldown_seconds)
        self.pnl_limit = Decimal(str(pnl_limit)) if pnl_limit is not None else None

        # In-memory state
        self._positions: Dict[str, Decimal] = {}
        self._last_order_ts: Dict[str, float] = {}
        self.realized_pnl = Decimal("0")
        self.killed: bool = False
        self.kill_reason: Optional[str] = None
        self.kill_ts: Optional[float] = None

        # locks
        self._market_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def _get_market_lock(self, market_id: str) -> asyncio.Lock:
        if market_id not in self._market_locks:
            self._market_locks[market_id] = asyncio.Lock()
        return self._market_locks[market_id]

    async def can_open_position(self, market_id: str, size: Decimal) -> Tuple[bool, Optional[str]]:
        if self.killed:
            return False, f"KILL_SWITCH: {self.kill_reason}"

        try:
            size_d = Decimal(str(size))
        except (InvalidOperation, TypeError):
            raise ValueError("size must be a numeric value")

        if size_d <= 0:
            raise ValueError("size must be > 0")

        if size_d > self.max_order_size_val:
            return False, "exceeds max_order_size"

        # cooldown and position checks per market
        lock = self._get_market_lock(market_id)
        async with lock:
            now = time.time()
            last_ts = self._last_order_ts.get(market_id)
            if last_ts is not None and (now - last_ts) < self.cooldown_seconds:
                return False, "cooldown"

            current_pos = self._positions.get(market_id, Decimal("0"))
            if (current_pos + size_d) > self.max_position_size_val:
                return False, "max_position_size_reached"

            return True, None

    async def commit_open_position(self, market_id: str, size: Decimal) -> None:
        try:
            size_d = Decimal(str(size))
        except (InvalidOperation, TypeError):
            raise ValueError("size must be a numeric value")

        if size_d <= 0:
            raise ValueError("size must be > 0")

        lock = self._get_market_lock(market_id)
        async with lock:
            self._positions[market_id] = self._positions.get(market_id, Decimal("0")) + size_d
            self._last_order_ts[market_id] = time.time()

    async def update_pnl(self, realized_pnl: Decimal) -> None:
        try:
            pnl = Decimal(str(realized_pnl))
        except (InvalidOperation, TypeError):
            raise ValueError("realized_pnl must be numeric")

        async with self._global_lock:
            self.realized_pnl += pnl
            if self.pnl_limit is not None:
                # trigger kill switch if realized_pnl <= -pnl_limit
                if self.realized_pnl <= (self.pnl_limit * Decimal("-1")):
                    self.trigger_kill_switch("PNL_LIMIT")

    def trigger_kill_switch(self, reason: str) -> None:
        if not isinstance(reason, str):
            raise ValueError("reason must be a string")
        self.killed = True
        self.kill_reason = reason
        self.kill_ts = time.time()

    def max_position_size(self, market_id: str) -> Decimal:
        # For MVP, same across markets
        return Decimal(self.max_position_size_val)
