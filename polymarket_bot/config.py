"""Configuration loader for polymarket_bot

Precedence: explicit config dict > environment variables (including .env) > config.yaml
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional, cast
import yaml

from polymarket_bot.runtime.policy import resolve_execution_mode


def _load_dotenv(path: Path) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def _load_yaml(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf8") as fh:
            raw = yaml.safe_load(fh) or {}
            if not isinstance(raw, dict):
                return {}
            return cast(Dict[str, object], raw)
    except Exception:
        return {}


def load_config(override: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    """Return configuration dict following precedence rules.

    override: explicit config dict (highest precedence)
    """
    # Start with config.yaml (lowest)
    root = Path.cwd()
    cfg: Dict[str, object] = {}
    cfg_yaml = _load_yaml(root / "config.yaml")
    cfg.update(cfg_yaml)

    # Load .env into os.environ-like dict
    dotenv_vals = _load_dotenv(root / ".env")
    for k, v in dotenv_vals.items():
        # Don't overwrite real environment variables
        if k not in os.environ:
            os.environ[k] = v

    # Now read environment variables
    env_map: Dict[str, object] = {
        "API_KEY": os.environ.get("API_KEY"),
        "API_SECRET": os.environ.get("API_SECRET"),
        "PAPER_MODE": os.environ.get("PAPER_MODE"),
        "EXECUTION_MODE": os.environ.get("EXECUTION_MODE"),
        "LIVE_ENABLED": os.environ.get("LIVE_ENABLED"),
        "ADAPTER_KIND": os.environ.get("ADAPTER_KIND"),
        "ADAPTER_API_KEY": os.environ.get("ADAPTER_API_KEY"),
        "ADAPTER_API_SECRET": os.environ.get("ADAPTER_API_SECRET"),
        "RUNTIME_PREFLIGHT_PROBE": os.environ.get("RUNTIME_PREFLIGHT_PROBE"),
        "RUNTIME_PREFLIGHT_PROBE_TIMEOUT_SEC": os.environ.get("RUNTIME_PREFLIGHT_PROBE_TIMEOUT_SEC"),
        "RUNTIME_PREFLIGHT_PROBE_MAX_ATTEMPTS": os.environ.get("RUNTIME_PREFLIGHT_PROBE_MAX_ATTEMPTS"),
        "RUNTIME_ADAPTER_TIMEOUT_SEC": os.environ.get("RUNTIME_ADAPTER_TIMEOUT_SEC"),
        "RUNTIME_MAX_CONSECUTIVE_ADAPTER_FAILURES": os.environ.get("RUNTIME_MAX_CONSECUTIVE_ADAPTER_FAILURES"),
        "RISK_MAX_POSITION": os.environ.get("RISK_MAX_POSITION"),
        "RISK_MAX_ORDER_SIZE": os.environ.get("RISK_MAX_ORDER_SIZE"),
        "RISK_COOLDOWN_SEC": os.environ.get("RISK_COOLDOWN_SEC"),
        "RISK_PNL_LIMIT": os.environ.get("RISK_PNL_LIMIT"),
        "RUNTIME_TICK_SECONDS": os.environ.get("RUNTIME_TICK_SECONDS"),
        "RUNTIME_MAX_TICKS": os.environ.get("RUNTIME_MAX_TICKS"),
        "RUNTIME_EVENTS_PATH": os.environ.get("RUNTIME_EVENTS_PATH"),
        "RUNTIME_MARKET_ID": os.environ.get("RUNTIME_MARKET_ID"),
        "CONFIG_FILE": os.environ.get("CONFIG_FILE"),
    }

    # Normalize PAPER_MODE to boolean if present
    if env_map.get("PAPER_MODE") is not None:
        env_map["PAPER_MODE"] = str(env_map["PAPER_MODE"]).lower() == "true"

    # Merge env_map into cfg (env overrides yaml)
    for env_key, env_val in env_map.items():
        if env_val is not None:
            cfg[env_key] = env_val

    # Finally, apply explicit override
    if override:
        cfg.update(override)

    # Normalize execution mode contract with legacy PAPER_MODE compatibility.
    mode = resolve_execution_mode(
        execution_mode=cfg.get("EXECUTION_MODE"),
        paper_mode=cfg.get("PAPER_MODE"),
    )
    cfg["EXECUTION_MODE"] = mode.value
    cfg["PAPER_MODE"] = mode.value == "paper"

    return cfg
