from __future__ import annotations


class AdapterError(Exception):
    """Base adapter-layer error."""


class AdapterConfigError(AdapterError):
    """Invalid or missing adapter configuration."""


class AdapterConnectivityError(AdapterError):
    """Connectivity/transport failure when talking to exchange."""


class AdapterTimeoutError(AdapterError):
    """Operation timed out at adapter boundary."""


class AdapterRateLimitError(AdapterError):
    """Rate limit encountered."""


class AdapterOrderRejectedError(AdapterError):
    """Order rejected by exchange/business rules."""


class AdapterGuardrailError(AdapterError):
    """Local guardrail/policy violation (mode, unsafe path, etc.)."""
