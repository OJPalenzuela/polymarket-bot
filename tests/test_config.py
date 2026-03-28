import pytest

from polymarket_bot.config import load_config
from polymarket_bot.runtime.policy import ExecutionMode, resolve_execution_mode


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


def test_execution_mode_defaults_to_paper(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EXECUTION_MODE", raising=False)
    monkeypatch.delenv("PAPER_MODE", raising=False)

    cfg = load_config()
    assert cfg.get("EXECUTION_MODE") == "paper"
    assert cfg.get("PAPER_MODE") is True


def test_execution_mode_invalid_fails_fast():
    with pytest.raises(ValueError, match="invalid execution_mode"):
        resolve_execution_mode(execution_mode="banana", paper_mode=None)


def test_legacy_paper_mode_mapping_deterministic(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PAPER_MODE", "false")
    monkeypatch.delenv("EXECUTION_MODE", raising=False)

    cfg = load_config()
    assert cfg.get("EXECUTION_MODE") == ExecutionMode.LIVE.value
    assert cfg.get("PAPER_MODE") is False

    monkeypatch.setenv("PAPER_MODE", "true")
    cfg2 = load_config()
    assert cfg2.get("EXECUTION_MODE") == ExecutionMode.PAPER.value
    assert cfg2.get("PAPER_MODE") is True


def test_execution_mode_precedence_over_legacy_paper_mode(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PAPER_MODE", "true")
    monkeypatch.setenv("EXECUTION_MODE", "shadow_live")

    cfg = load_config()
    assert cfg.get("EXECUTION_MODE") == "shadow_live"
    assert cfg.get("PAPER_MODE") is False
