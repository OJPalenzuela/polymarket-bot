import asyncio

from polymarket_bot.adapters.base import ExchangeAdapter
from polymarket_bot.adapters.errors import AdapterConnectivityError
from polymarket_bot.adapters.fake import FakeAdapter
from polymarket_bot.runtime.policy import ExecutionMode, build_execution_policy
from polymarket_bot.runtime.preflight import run_preflight
from polymarket_bot.runtime.safety import RuntimeSafetyConfig


class FlakyProbeAdapter(FakeAdapter):
    def __init__(self, *, failures_before_success: int):
        super().__init__(paper_mode=False)
        self.failures_before_success = failures_before_success
        self.attempts = 0

    async def probe_connectivity(self) -> None:
        self.attempts += 1
        if self.attempts <= self.failures_before_success:
            raise AdapterConnectivityError("probe failed")


class AlwaysTimeoutProbeAdapter(FakeAdapter):
    def __init__(self):
        super().__init__(paper_mode=False)
        self.attempts = 0

    async def probe_connectivity(self) -> None:
        self.attempts += 1
        raise TimeoutError("forced timeout")


class NoProbeAdapter(ExchangeAdapter):
    def __init__(self):
        super().__init__(paper_mode=False)


def test_preflight_paper_passes_without_live_secrets():
    cfg = {}
    policy = build_execution_policy(ExecutionMode.PAPER)
    adapter = FakeAdapter(paper_mode=True)
    safety = RuntimeSafetyConfig()

    result = asyncio.run(run_preflight(cfg=cfg, policy=policy, adapter=adapter, safety=safety))
    assert result.ok is True
    assert result.mode == "paper"


def test_preflight_shadow_rejects_missing_required_config():
    cfg = {"ADAPTER_KIND": "fake"}
    policy = build_execution_policy(ExecutionMode.SHADOW_LIVE)
    adapter = FakeAdapter(paper_mode=False)
    safety = RuntimeSafetyConfig()

    result = asyncio.run(run_preflight(cfg=cfg, policy=policy, adapter=adapter, safety=safety))
    assert result.ok is False
    assert result.reason_class == "preflight_config"
    assert any(x.startswith("missing_required_config") for x in result.checks_failed)


def test_preflight_live_requires_explicit_opt_in():
    cfg = {
        "ADAPTER_KIND": "fake",
        "ADAPTER_API_KEY": "k",
        "ADAPTER_API_SECRET": "s",
        "LIVE_ENABLED": False,
    }
    policy = build_execution_policy(ExecutionMode.LIVE)
    adapter = FakeAdapter(paper_mode=False)
    safety = RuntimeSafetyConfig()

    result = asyncio.run(run_preflight(cfg=cfg, policy=policy, adapter=adapter, safety=safety))
    assert result.ok is False
    assert result.reason_class == "preflight_opt_in"


def test_preflight_live_rejects_missing_required_config():
    cfg = {
        "ADAPTER_KIND": "fake",
        "ADAPTER_API_KEY": "k",
        # ADAPTER_API_SECRET intentionally missing
        "LIVE_ENABLED": True,
    }
    policy = build_execution_policy(ExecutionMode.LIVE)
    adapter = FakeAdapter(paper_mode=False)
    safety = RuntimeSafetyConfig()

    result = asyncio.run(run_preflight(cfg=cfg, policy=policy, adapter=adapter, safety=safety))
    assert result.ok is False
    assert result.reason_class == "preflight_config"
    assert any(x.startswith("missing_required_config:ADAPTER_API_SECRET") for x in result.checks_failed)


def test_preflight_shadow_rejects_invalid_adapter_probe_config():
    cfg = {
        "ADAPTER_KIND": "custom",
        "ADAPTER_API_KEY": "k",
        "ADAPTER_API_SECRET": "s",
    }
    policy = build_execution_policy(ExecutionMode.SHADOW_LIVE)
    adapter = NoProbeAdapter()
    safety = RuntimeSafetyConfig()

    result = asyncio.run(run_preflight(cfg=cfg, policy=policy, adapter=adapter, safety=safety))
    assert result.ok is False
    assert result.reason_class == "preflight_adapter_capability"


def test_preflight_probe_retries_bounded_and_succeeds():
    cfg = {
        "ADAPTER_KIND": "fake",
        "ADAPTER_API_KEY": "k",
        "ADAPTER_API_SECRET": "s",
        "LIVE_ENABLED": True,
    }
    policy = build_execution_policy(ExecutionMode.LIVE)
    adapter = FlakyProbeAdapter(failures_before_success=1)
    safety = RuntimeSafetyConfig(preflight_probe_max_attempts=2)

    result = asyncio.run(run_preflight(cfg=cfg, policy=policy, adapter=adapter, safety=safety))
    assert result.ok is True
    assert "connectivity_probe_attempts:2" in result.checks_passed


def test_preflight_probe_retry_exhaustion_is_deterministic_failure():
    cfg = {
        "ADAPTER_KIND": "fake",
        "ADAPTER_API_KEY": "k",
        "ADAPTER_API_SECRET": "s",
        "LIVE_ENABLED": True,
    }
    policy = build_execution_policy(ExecutionMode.LIVE)
    adapter = FlakyProbeAdapter(failures_before_success=3)
    safety = RuntimeSafetyConfig(preflight_probe_max_attempts=2)

    result = asyncio.run(run_preflight(cfg=cfg, policy=policy, adapter=adapter, safety=safety))
    assert result.ok is False
    assert result.reason_class == "preflight_connectivity"
    assert "connectivity_probe_attempts:2" in result.checks_failed


def test_preflight_probe_timeout_exhaustion_is_deterministic_failure():
    cfg = {
        "ADAPTER_KIND": "fake",
        "ADAPTER_API_KEY": "k",
        "ADAPTER_API_SECRET": "s",
        "LIVE_ENABLED": True,
    }
    policy = build_execution_policy(ExecutionMode.LIVE)
    adapter = AlwaysTimeoutProbeAdapter()
    safety = RuntimeSafetyConfig(preflight_probe_timeout_sec=0.001, preflight_probe_max_attempts=2)

    result = asyncio.run(run_preflight(cfg=cfg, policy=policy, adapter=adapter, safety=safety))
    assert result.ok is False
    assert result.reason_class == "preflight_connectivity"
    assert "connectivity_probe_attempts:2" in result.checks_failed
