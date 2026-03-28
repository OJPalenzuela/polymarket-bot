from .clock import ClockNow, SleepFn, default_clock_now, default_sleep, utc_iso, monotonic_seconds

__all__ = [
    "ClockNow",
    "SleepFn",
    "default_clock_now",
    "default_sleep",
    "utc_iso",
    "monotonic_seconds",
    "RuntimeOrchestrator",
    "RuntimeSummary",
]


def __getattr__(name: str):
    if name in {"RuntimeOrchestrator", "RuntimeSummary"}:
        from .orchestrator import RuntimeOrchestrator, RuntimeSummary

        exports = {
            "RuntimeOrchestrator": RuntimeOrchestrator,
            "RuntimeSummary": RuntimeSummary,
        }
        return exports[name]
    raise AttributeError(name)
