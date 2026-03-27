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
