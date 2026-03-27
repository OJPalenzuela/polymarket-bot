"""polymarket_bot package

Exports a create_client factory (placeholder for Sprint 3 implementation).
"""
from typing import Any


def create_client(*, paper_mode: bool | None = None, config: dict | None = None) -> Any:
    """Minimal placeholder create_client for import-time safety.

    Sprint 3 will provide full implementation. For now, return a simple namespace
    with _paper_mode set according to env/config if provided.
    """
    # Lazy import to avoid heavy deps
    from .config import load_config

    cfg = load_config(config)
    # Respect explicit arg if provided
    pm = paper_mode if paper_mode is not None else cfg.get("PAPER_MODE", False)

    class _Client:
        def __init__(self, paper_mode):
            self._paper_mode = bool(paper_mode)

        def __repr__(self):
            return f"<Client paper_mode={self._paper_mode}>"

    return _Client(pm)
