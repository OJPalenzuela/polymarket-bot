"""Configuration loader for polymarket_bot

Precedence: explicit config dict > environment variables (including .env) > config.yaml
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional
import yaml


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
            return yaml.safe_load(fh) or {}
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
    env_map = {
        "API_KEY": os.environ.get("API_KEY"),
        "API_SECRET": os.environ.get("API_SECRET"),
        "PAPER_MODE": os.environ.get("PAPER_MODE"),
        "RISK_MAX_POSITION": os.environ.get("RISK_MAX_POSITION"),
        "RISK_MAX_ORDER_SIZE": os.environ.get("RISK_MAX_ORDER_SIZE"),
        "RISK_COOLDOWN_SEC": os.environ.get("RISK_COOLDOWN_SEC"),
        "RISK_PNL_LIMIT": os.environ.get("RISK_PNL_LIMIT"),
        "CONFIG_FILE": os.environ.get("CONFIG_FILE"),
    }

    # Normalize PAPER_MODE to boolean if present
    if env_map.get("PAPER_MODE") is not None:
        env_map["PAPER_MODE"] = str(env_map["PAPER_MODE"]).lower() == "true"

    # Merge env_map into cfg (env overrides yaml)
    for k, v in env_map.items():
        if v is not None:
            cfg[k] = v

    # Finally, apply explicit override
    if override:
        cfg.update(override)

    return cfg
