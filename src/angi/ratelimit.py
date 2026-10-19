import asyncio
import time
from collections import deque

_PRUNE_EVERY = 100


class SlidingWindow:
    """Per-key request counter over a rolling window. Single-process, in-memory."""

    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window_s = window_s
        self.hits: dict[str, deque[float]] = {}
        self._calls = 0

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        dq = self.hits.setdefault(key, deque())
        cutoff = now - self.window_s
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= self.limit:
            return False
        dq.append(now)
        self._prune()
        return True

    def _prune(self) -> None:
        self._calls += 1
        if self._calls % _PRUNE_EVERY == 0:
            self.hits = {k: v for k, v in self.hits.items() if v}


class GpuGate:
    """Serializes LLM work and caps concurrent waiters. When full, angi falls
    back to canned lines instead of erroring."""

    def __init__(self, max_queue: int):
        self.sem = asyncio.Semaphore(1)
        self.max_queue = max_queue
        self.waiting = 0

    @property
    def full(self) -> bool:
        return self.waiting >= self.max_queue
