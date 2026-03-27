from __future__ import annotations

from decimal import Decimal
from typing import Dict
import time

from .base import ExchangeAdapter


class FakeAdapter(ExchangeAdapter):
    """A deterministic, no-I/O adapter to simulate exchange behavior.

    place_limit_order returns a dict with keys: exchange_order_id, filled_size, avg_price
    and does not perform any network I/O. It respects paper_mode but for the MVP we
    allow FakeAdapter to operate in both modes deterministically.
    """

    def __init__(self, *, paper_mode: bool = True) -> None:
        super().__init__(paper_mode=paper_mode)

    async def place_limit_order(self, order: Dict) -> Dict:
        # No network I/O. Produce deterministic ids based on timestamp and client_id if present
        ts = int(time.time())
        client_id = order.get("client_id") or "anon"
        exchange_order_id = f"fake-{client_id}-{ts}"

        # Use Decimal for numeric fields, but return floats for JSON-friendly output
        price = Decimal(str(order.get("price")))
        size = Decimal(str(order.get("size")))

        return {
            "exchange_order_id": exchange_order_id,
            "filled_size": float(size),
            "avg_price": float(price),
        }
