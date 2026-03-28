from __future__ import annotations

from decimal import Decimal
from typing import Dict

from .base import ExchangeAdapter
from .errors import AdapterGuardrailError


class FakeAdapter(ExchangeAdapter):
    """A deterministic, no-I/O adapter to simulate exchange behavior.

    place_limit_order returns a dict with keys: exchange_order_id, filled_size, avg_price
    and does not perform any network I/O. It respects paper_mode but for the MVP we
    allow FakeAdapter to operate in both modes deterministically.
    """

    def __init__(self, *, paper_mode: bool = True) -> None:
        super().__init__(paper_mode=paper_mode)

    @property
    def supports_connectivity_probe(self) -> bool:
        # Deterministic synthetic probe support for tests/smoke.
        return True

    @property
    def supports_live_orders(self) -> bool:
        # Fake adapter keeps deterministic simulation, but can model live path contracts.
        return True

    async def probe_connectivity(self) -> None:
        # Synthetic probe: deterministic success by default.
        return None

    async def place_limit_order(self, order: Dict) -> Dict:
        if order.get("order_type") != "limit":
            raise AdapterGuardrailError("only limit orders are supported in PR3")

        # No network I/O. Produce deterministic ids based on client_id.
        client_id = order.get("client_id") or "anon"
        exchange_order_id = f"fake-{client_id}"

        # Use Decimal for numeric fields, but return floats for JSON-friendly output
        price = Decimal(str(order.get("price")))
        size = Decimal(str(order.get("size")))

        return {
            "exchange_order_id": exchange_order_id,
            "filled_size": float(size),
            "avg_price": float(price),
        }
