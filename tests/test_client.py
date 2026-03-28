from polymarket_bot.adapters.fake import FakeAdapter
from polymarket_bot.adapters.errors import AdapterConnectivityError
from polymarket_bot.client import create_client


def test_create_client_respects_paper_mode(monkeypatch):
    # Ensure that create_client with paper_mode True uses FakeAdapter and sets flag
    client = create_client(paper_mode=True)
    assert client._paper_mode is True
    assert isinstance(client.adapter, FakeAdapter)


def test_create_client_defaults_to_paper_mode():
    client = create_client(config={})
    assert client.execution_mode.value == "paper"
    assert client._paper_mode is True


def test_place_order_simulated_response():
    client = create_client(paper_mode=True)
    order = {
        "market_id": "m1",
        "side": "buy",
        "price": 12.5,
        "size": 1.0,
        "order_type": "limit",
        "client_id": "test-1",
    }

    resp = client.place_order(order)
    assert resp["status"] == "simulated"
    assert resp["simulated"] is True
    assert resp["order_id"].startswith("fake-")
    assert resp["avg_price"] == 12.5


def test_shadow_live_suppresses_order_placement():
    client = create_client(
        config={
            "EXECUTION_MODE": "shadow_live",
            "PAPER_MODE": False,
            "RISK_MAX_ORDER_SIZE": "10",
            "RISK_MAX_POSITION": "100",
            "RISK_COOLDOWN_SEC": "0",
        }
    )
    order = {
        "market_id": "m1",
        "side": "buy",
        "price": 12.5,
        "size": 1.0,
        "order_type": "limit",
        "client_id": "test-shadow",
    }
    resp = client.place_order(order)
    assert resp["status"] == "rejected"
    assert resp["rejection_reason"] == "shadow_live_read_only"
    assert resp["retry_decision"] == "no_blind_retry"


def test_live_adapter_error_maps_without_blind_retry():
    class FailingAdapter(FakeAdapter):
        async def place_limit_order(self, order):
            raise AdapterConnectivityError("boom")

    client = create_client(
        config={
            "EXECUTION_MODE": "live",
            "LIVE_ENABLED": True,
            "ADAPTER_KIND": "fake",
            "ADAPTER_API_KEY": "k",
            "ADAPTER_API_SECRET": "s",
            "RISK_MAX_ORDER_SIZE": "10",
            "RISK_MAX_POSITION": "100",
            "RISK_COOLDOWN_SEC": "0",
        },
        adapter=FailingAdapter(paper_mode=False),
    )
    order = {
        "market_id": "m1",
        "side": "buy",
        "price": 12.5,
        "size": 1.0,
        "order_type": "limit",
        "client_id": "test-live",
    }
    resp = client.place_order(order)
    assert resp["status"] == "rejected"
    assert resp["error_type"] == "adapter_connectivity"
    assert resp["retry_decision"] == "no_blind_retry"
    assert resp["retry_count"] == 0


def test_live_success_marks_submitted_and_not_simulated():
    client = create_client(
        config={
            "EXECUTION_MODE": "live",
            "LIVE_ENABLED": True,
            "ADAPTER_KIND": "fake",
            "ADAPTER_API_KEY": "k",
            "ADAPTER_API_SECRET": "s",
            "RISK_MAX_ORDER_SIZE": "10",
            "RISK_MAX_POSITION": "100",
            "RISK_COOLDOWN_SEC": "0",
        },
        adapter=FakeAdapter(paper_mode=False),
    )
    order = {
        "market_id": "m1",
        "side": "buy",
        "price": 12.5,
        "size": 1.0,
        "order_type": "limit",
        "client_id": "test-live-ok",
    }
    resp = client.place_order(order)
    assert resp["status"] == "submitted"
    assert resp["simulated"] is False


def test_place_order_returns_rejection_when_risk_rejects(monkeypatch):
    # Create client with small max order size via config override
    cfg = {"RISK_MAX_ORDER_SIZE": "0.5", "RISK_MAX_POSITION": "1", "RISK_COOLDOWN_SEC": "0"}
    client = create_client(paper_mode=True, config=cfg)

    order = {
        "market_id": "m1",
        "side": "buy",
        "price": 12.5,
        "size": 1.0,
        "order_type": "limit",
    }

    resp = client.place_order(order)
    assert resp["status"] == "rejected"
    assert resp["rejection_reason"] is not None


def test_create_client_accepts_adapter_override():
    fake = FakeAdapter(paper_mode=True)
    client = create_client(paper_mode=True, adapter=fake)
    assert client.adapter is fake
