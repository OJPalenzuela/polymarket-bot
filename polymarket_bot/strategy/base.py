from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional, Literal


@dataclass(frozen=True)
class TickContext:
    run_id: str
    tick_id: int
    tick_ts: str
    market_id: str


@dataclass(frozen=True)
class OrderIntent:
    market_id: str
    side: Literal["buy", "sell"]
    price: float
    size: float
    order_type: Literal["limit"] = "limit"
    client_id: Optional[str] = None

    def to_order_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "side": self.side,
            "price": self.price,
            "size": self.size,
            "order_type": self.order_type,
            "client_id": self.client_id,
        }


class Strategy(Protocol):
    async def on_tick(self, ctx: TickContext) -> OrderIntent | None:
        ...
