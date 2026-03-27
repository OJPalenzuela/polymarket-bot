from __future__ import annotations

from typing import Any


class ExchangeAdapter:
    """Base adapter interface.

    Network-capable methods MUST raise RuntimeError when self.paper_mode is True to
    prevent accidental I/O in PAPER_MODE. Real adapters should inherit and implement
    network methods. FakeAdapter may override this behavior to simulate responses.
    """

    def __init__(self, *, paper_mode: bool = False) -> None:
        self.paper_mode = bool(paper_mode)

    async def place_limit_order(self, order: dict) -> dict:
        """Place a limit order on the exchange.

        Real adapters SHOULD perform network I/O here. To be paper-mode safe, this
        base implementation prevents network usage by raising when paper_mode True.
        """
        if self.paper_mode:
            raise RuntimeError("network method cannot be called in paper_mode")
        raise NotImplementedError("place_limit_order must be implemented by adapter")
