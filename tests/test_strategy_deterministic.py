import asyncio

from polymarket_bot.strategy import DeterministicStrategy, TickContext


def _mk_ctx(run_id: str, tick_id: int) -> TickContext:
    return TickContext(
        run_id=run_id,
        tick_id=tick_id,
        tick_ts=f"2026-01-01T00:00:0{tick_id}Z",
        market_id="m1",
    )


def test_strategy_contract_returns_order_intent_or_none():
    strategy = DeterministicStrategy(default_size=1.0, base_price=0.5)

    intent = asyncio.run(strategy.on_tick(_mk_ctx("run-a", 1)))
    noop = asyncio.run(strategy.on_tick(_mk_ctx("run-a", 2)))

    assert intent is not None
    assert intent.market_id == "m1"
    assert intent.side in ("buy", "sell")
    assert isinstance(intent.price, float)
    assert isinstance(intent.size, float)
    assert intent.order_type == "limit"
    assert noop is None


def test_deterministic_outputs_for_identical_sequence():
    strategy = DeterministicStrategy(default_size=1.0, base_price=0.5)
    seq = [_mk_ctx("run-fixed", i) for i in range(1, 6)]

    out_a = [asyncio.run(strategy.on_tick(ctx)) for ctx in seq]
    out_b = [asyncio.run(strategy.on_tick(ctx)) for ctx in seq]

    assert out_a == out_b


def test_deterministic_noop_branch_even_ticks():
    strategy = DeterministicStrategy()
    even_ctx = _mk_ctx("run-a", 10)
    assert asyncio.run(strategy.on_tick(even_ctx)) is None
