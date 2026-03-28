import os

from polymarket_bot.config import load_config


def test_env_config_loading(monkeypatch, tmp_path):
    # Ensure no .env file present to interfere
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("PAPER_MODE", "true")
    monkeypatch.setenv("RISK_MAX_ORDER_SIZE", "5.0")

    cfg = load_config()

    assert cfg.get("PAPER_MODE") is True
    assert str(cfg.get("RISK_MAX_ORDER_SIZE")) == "5.0"


def test_runtime_env_config_loading(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("RUNTIME_TICK_SECONDS", "0.5")
    monkeypatch.setenv("RUNTIME_MAX_TICKS", "7")
    monkeypatch.setenv("RUNTIME_EVENTS_PATH", "./tmp/events.jsonl")
    monkeypatch.setenv("RUNTIME_MARKET_ID", "market-abc")

    cfg = load_config()

    assert str(cfg.get("RUNTIME_TICK_SECONDS")) == "0.5"
    assert str(cfg.get("RUNTIME_MAX_TICKS")) == "7"
    assert cfg.get("RUNTIME_EVENTS_PATH") == "./tmp/events.jsonl"
    assert cfg.get("RUNTIME_MARKET_ID") == "market-abc"
