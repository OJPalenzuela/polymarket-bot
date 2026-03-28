from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Any, Dict, Optional


VALID_EVENT_TYPES = {
    "runtime_started",
    "tick_started",
    "strategy_decision",
    "order_result",
    "tick_completed",
    "runtime_stopped",
    "runtime_error",
}


@dataclass(frozen=True)
class RuntimeEvent:
    event_id: str
    event_type: str
    ts: str
    run_id: str
    tick_id: Optional[int]
    level: str
    component: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "ts": self.ts,
            "run_id": self.run_id,
            "tick_id": self.tick_id,
            "level": self.level,
            "component": self.component,
            "payload": self.payload,
        }


def make_event(
    *,
    event_type: str,
    ts: str,
    run_id: str,
    tick_id: Optional[int],
    level: str,
    component: str,
    payload: Dict[str, Any] | None = None,
) -> RuntimeEvent:
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"invalid runtime event_type: {event_type}")
    return RuntimeEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        ts=ts,
        run_id=run_id,
        tick_id=tick_id,
        level=level,
        component=component,
        payload=payload or {},
    )
