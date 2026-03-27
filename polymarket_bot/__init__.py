"""polymarket_bot package

Exports a create_client factory (placeholder for Sprint 3 implementation).
"""
from __future__ import annotations

from typing import Any, Optional

from .client import create_client  # re-export the factory

__all__ = ["create_client"]
