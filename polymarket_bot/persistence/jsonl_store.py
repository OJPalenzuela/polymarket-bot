from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from polymarket_bot.logging.events import RuntimeEvent


class EventStore(Protocol):
    async def append(self, event: RuntimeEvent) -> None:
        ...


class JSONLEventStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def append(self, event: RuntimeEvent) -> None:
        payload = json.dumps(event.to_dict(), ensure_ascii=False)
        self._append_line(payload)

    def _append_line(self, line: str) -> None:
        tries = 0
        while True:
            tries += 1
            try:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.write("\n")
                return
            except OSError:
                if tries >= 2:
                    raise
