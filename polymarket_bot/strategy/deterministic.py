from __future__ import annotations

from .base import TickContext, OrderIntent, Strategy


class DeterministicStrategy(Strategy):
    """Simple deterministic strategy for PR2.

    - Odd tick_id => create deterministic BUY limit order intent
    - Even tick_id => NO_ACTION (None)
    """

    def __init__(self, *, default_size: float = 1.0, base_price: float = 0.50) -> None:
        self.default_size = float(default_size)
        self.base_price = float(base_price)

    async def on_tick(self, ctx: TickContext) -> OrderIntent | None:
        if ctx.tick_id % 2 == 0:
            return None

        # Deterministic transform from tick_id.
        step = (ctx.tick_id % 5) * 0.01
        price = round(self.base_price + step, 2)
        return OrderIntent(
            market_id=ctx.market_id,
            side="buy",
            price=price,
            size=self.default_size,
            order_type="limit",
            client_id=f"{ctx.run_id}-tick-{ctx.tick_id}",
        )
