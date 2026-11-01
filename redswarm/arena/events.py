from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import AsyncIterator


class EventBus:
    """In-process pub/sub with a short history for page loads."""

    def __init__(self, history: int = 200) -> None:
        self.history: deque[dict] = deque(maxlen=history)
        self._subs: set[asyncio.Queue] = set()

    def publish(self, type_: str, data: dict) -> None:
        event = {"type": type_, "data": data, "ts": time.time()}
        self.history.append(event)
        for q in self._subs:
            q.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs.discard(q)
