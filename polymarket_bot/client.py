from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any
import datetime
import asyncio

from .config import load_config
from .risk.risk_manager import RiskManager
from .adapters.base import ExchangeAdapter
from .adapters.fake import FakeAdapter
from .adapters.errors import (
    AdapterConfigError,
    AdapterConnectivityError,
    AdapterError,
    AdapterGuardrailError,
    AdapterOrderRejectedError,
    AdapterRateLimitError,
    AdapterTimeoutError,
)
from .runtime.policy import ExecutionMode
from .runtime.safety import RuntimeSafetyConfig


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
    def __init__(
        self,
        *,
        adapter: ExchangeAdapter,
        risk: RiskManager,
        paper_mode: bool,
        execution_mode: ExecutionMode,
        safety: RuntimeSafetyConfig,
    ):
        self.adapter = adapter
        self.risk = risk
        self._paper_mode = bool(paper_mode)
        self.execution_mode = execution_mode
        self.safety = safety

    def _base_result(self) -> Dict[str, Any]:
        return {
            "order_id": None,
            "status": "rejected",
            "filled_size": 0.0,
            "avg_price": None,
            "timestamp": _now_iso(),
            "simulated": True,
            "rejection_reason": None,
        }

    def _error_result(self, *, rejection_reason: str, error_type: str, stage: str) -> Dict[str, Any]:
        result = self._base_result()
        result["rejection_reason"] = rejection_reason
        result["error_type"] = error_type
        result["stage"] = stage
        result["retry_decision"] = "no_blind_retry"
        result["retry_count"] = 0
        return result

    def _map_adapter_error(self, exc: Exception) -> tuple[str, str]:
        if isinstance(exc, AdapterConfigError):
            return "adapter_config", "adapter_config"
        if isinstance(exc, AdapterConnectivityError):
            return "adapter_connectivity", "adapter_connectivity"
        if isinstance(exc, AdapterTimeoutError):
            return "adapter_timeout", "adapter_timeout"
        if isinstance(exc, AdapterRateLimitError):
            return "adapter_rate_limit", "adapter_rate_limit"
        if isinstance(exc, AdapterOrderRejectedError):
            return "adapter_order_rejected", "adapter_order_rejected"
        if isinstance(exc, AdapterGuardrailError):
            return "adapter_guardrail", "adapter_guardrail"
        if isinstance(exc, AdapterError):
            return "adapter_error", "adapter_error"
        if isinstance(exc, asyncio.TimeoutError):
            return "adapter_timeout", "adapter_timeout"
        return "adapter_unknown", "adapter_unknown"

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
            result = self._base_result()
            result["rejection_reason"] = reason
            return result

        if self.execution_mode == ExecutionMode.SHADOW_LIVE:
            result = self._base_result()
            result["rejection_reason"] = "shadow_live_read_only"
            result["error_type"] = "mode_guardrail"
            result["stage"] = "policy"
            result["retry_decision"] = "no_blind_retry"
            result["retry_count"] = 0
            return result

        if self.execution_mode == ExecutionMode.LIVE and not self.adapter.supports_live_orders:
            return self._error_result(
                rejection_reason="live_mode_requires_live_order_capability",
                error_type="mode_guardrail",
                stage="policy",
            )

        # Place order via adapter
        # No blind order retries in PR3: one bounded attempt only.
        try:
            resp = await asyncio.wait_for(
                self.adapter.place_limit_order(
                    {
                        "market_id": order.market_id,
                        "side": order.side,
                        "price": float(order.price),
                        "size": float(order.size),
                        "order_type": order.order_type,
                        "client_id": order.client_id,
                    }
                ),
                timeout=self.safety.adapter_order_timeout_sec,
            )
        except Exception as exc:
            rejection_reason, error_type = self._map_adapter_error(exc)
            return self._error_result(
                rejection_reason=rejection_reason,
                error_type=error_type,
                stage="adapter_order",
            )

        # Commit risk after successful placement
        await self.risk.commit_open_position(order.market_id, order.size)

        return {
            "order_id": resp.get("exchange_order_id"),
            "status": "simulated" if self.execution_mode != ExecutionMode.LIVE else "submitted",
            "filled_size": resp.get("filled_size"),
            "avg_price": resp.get("avg_price"),
            "timestamp": _now_iso(),
            "simulated": self.execution_mode != ExecutionMode.LIVE,
            "rejection_reason": None,
        }

    def place_order(self, order_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper that runs the async flow.

        For tests convenience we run the event loop if necessary.
        """
        import asyncio

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and running_loop.is_running():
            raise RuntimeError("place_order cannot be called from an active event loop; use place_order_async")

        return asyncio.run(self.place_order_async(order_dict))


def create_client(*, paper_mode: Optional[bool] = None, config: Optional[dict] = None, adapter: Optional[ExchangeAdapter] = None) -> Client:
    cfg = load_config(config)
    pm = paper_mode if paper_mode is not None else bool(cfg.get("PAPER_MODE", True))
    mode = ExecutionMode(str(cfg.get("EXECUTION_MODE", "paper")))
    safety = RuntimeSafetyConfig.from_config(cfg)

    def _as_int(value: object | None, default: int) -> int:
        if value is None:
            return default
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return default

    # RiskManager defaults (use small sane defaults if not provided)
    from decimal import Decimal

    max_pos = Decimal(str(cfg.get("RISK_MAX_POSITION", "10000")))
    max_order = Decimal(str(cfg.get("RISK_MAX_ORDER_SIZE", "1000")))
    cooldown = _as_int(cfg.get("RISK_COOLDOWN_SEC", 0), 0)
    pnl_limit = cfg.get("RISK_PNL_LIMIT")
    pnl_limit_d = Decimal(str(pnl_limit)) if pnl_limit is not None else None

    risk = RiskManager(max_pos, max_order, cooldown, pnl_limit_d)

    # Adapter resolution
    if adapter is None:
        # For MVP, default to FakeAdapter which is deterministic and safe
        adapter = FakeAdapter(paper_mode=pm)

    client = Client(adapter=adapter, risk=risk, paper_mode=pm, execution_mode=mode, safety=safety)
    return client
