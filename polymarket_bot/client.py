from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any
import datetime

from .config import load_config
from .risk.risk_manager import RiskManager
from .adapters.base import ExchangeAdapter
from .adapters.fake import FakeAdapter


@dataclass
class Order:
    market_id: str
    side: str
    price: Decimal
    size: Decimal
    order_type: str = "limit"
    client_id: Optional[str] = None


def _now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


class Client:
    def __init__(self, *, adapter: ExchangeAdapter, risk: RiskManager, paper_mode: bool):
        self.adapter = adapter
        self.risk = risk
        self._paper_mode = bool(paper_mode)

    def _validate_order_shape(self, order: Dict[str, Any]) -> None:
        required = ["market_id", "side", "price", "size", "order_type"]
        for k in required:
            if k not in order:
                raise ValueError(f"missing required field: {k}")

        if order["side"] not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")

        try:
            price = Decimal(str(order["price"]))
            size = Decimal(str(order["size"]))
        except (InvalidOperation, TypeError):
            raise ValueError("price and size must be numeric")

        if price <= 0 or size <= 0:
            raise ValueError("price and size must be > 0")

    async def place_order_async(self, order_dict: Dict[str, Any]) -> Dict[str, Any]:
        # Validate shape
        self._validate_order_shape(order_dict)

        order = Order(
            market_id=order_dict["market_id"],
            side=order_dict["side"],
            price=Decimal(str(order_dict["price"])),
            size=Decimal(str(order_dict["size"])),
            order_type=order_dict.get("order_type", "limit"),
            client_id=order_dict.get("client_id"),
        )

        allowed, reason = await self.risk.can_open_position(order.market_id, order.size)
        if not allowed:
            return {
                "order_id": None,
                "status": "rejected",
                "filled_size": 0.0,
                "avg_price": None,
                "timestamp": _now_iso(),
                "simulated": True,
                "rejection_reason": reason,
            }

        # Place order via adapter
        try:
            resp = await self.adapter.place_limit_order({
                "market_id": order.market_id,
                "side": order.side,
                "price": float(order.price),
                "size": float(order.size),
                "order_type": order.order_type,
                "client_id": order.client_id,
            })
        except RuntimeError:
            # Adapter indicated a paper_mode violation or network block
            raise

        # Commit risk after successful placement
        await self.risk.commit_open_position(order.market_id, order.size)

        return {
            "order_id": resp.get("exchange_order_id"),
            "status": "simulated",
            "filled_size": resp.get("filled_size"),
            "avg_price": resp.get("avg_price"),
            "timestamp": _now_iso(),
            "simulated": True,
            "rejection_reason": None,
        }

    def place_order(self, order_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper that runs the async flow.

        For tests convenience we run the event loop if necessary.
        """
        import asyncio

        return asyncio.get_event_loop().run_until_complete(self.place_order_async(order_dict))


def create_client(*, paper_mode: Optional[bool] = None, config: Optional[dict] = None, adapter: Optional[ExchangeAdapter] = None) -> Client:
    cfg = load_config(config)
    pm = paper_mode if paper_mode is not None else bool(cfg.get("PAPER_MODE", False))

    # RiskManager defaults (use small sane defaults if not provided)
    from decimal import Decimal

    max_pos = Decimal(str(cfg.get("RISK_MAX_POSITION", "10000")))
    max_order = Decimal(str(cfg.get("RISK_MAX_ORDER_SIZE", "1000")))
    cooldown = int(cfg.get("RISK_COOLDOWN_SEC", 0))
    pnl_limit = cfg.get("RISK_PNL_LIMIT")
    pnl_limit_d = Decimal(str(pnl_limit)) if pnl_limit is not None else None

    risk = RiskManager(max_pos, max_order, cooldown, pnl_limit_d)

    # Adapter resolution
    if adapter is None:
        # For MVP, default to FakeAdapter which is deterministic and safe
        adapter = FakeAdapter(paper_mode=pm)

    client = Client(adapter=adapter, risk=risk, paper_mode=pm)
    return client
