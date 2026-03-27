import pytest
import asyncio
from decimal import Decimal

from polymarket_bot.adapters.fake import FakeAdapter
from polymarket_bot.client import create_client


def test_create_client_respects_paper_mode(monkeypatch):
    # Ensure that create_client with paper_mode True uses FakeAdapter and sets flag
    client = create_client(paper_mode=True)
    assert client._paper_mode is True
    assert isinstance(client.adapter, FakeAdapter)


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
