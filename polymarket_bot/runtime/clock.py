from __future__ import annotations

import asyncio
import datetime
import time
from typing import Awaitable, Callable


ClockNow = Callable[[], datetime.datetime]
SleepFn = Callable[[float], Awaitable[None]]


def default_clock_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def utc_iso(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def monotonic_seconds() -> float:
    return time.monotonic()
