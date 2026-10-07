"""Snapshot cache that enforces the SportAPI data update guidelines.

An assistant may call the same tool several times in a row ("and now?", "what
about the odds?"). The Sport Line API asks clients not to request the same data
more often than a documented minimum interval and not to overlap requests for
the same data:
https://sportapi.net/docs/sport-line/getting-started/update-guidelines.html

Every API call of this server goes through :class:`SnapshotCache`: a response is
reused until its interval has passed, and concurrent calls for the same data wait
for the request already in flight instead of sending a second one.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Any, TypeVar

import anyio

T = TypeVar("T")

_MAX_ENTRIES = 512


class SnapshotCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[Hashable, tuple[float, float, Any]] = {}
        self._locks: dict[Hashable, anyio.Lock] = {}

    async def get(
        self, key: Hashable, ttl: float, fetch: Callable[[], Awaitable[T]]
    ) -> tuple[T, float]:
        """Return ``(value, age_in_seconds)``; ``fetch`` runs only when the cached
        snapshot is older than ``ttl`` seconds."""
        lock = self._locks.setdefault(key, anyio.Lock())
        async with lock:
            entry = self._entries.get(key)
            now = self._clock()
            if entry is not None and now < entry[1]:
                value: T = entry[2]
                return value, now - entry[0]
            value = await fetch()
            fetched = self._clock()
            self._entries[key] = (fetched, fetched + ttl, value)
            self._prune(fetched)
            return value, 0.0

    def _prune(self, now: float) -> None:
        if len(self._entries) <= _MAX_ENTRIES:
            return
        for key in [k for k, (_, expires, _) in self._entries.items() if expires <= now]:
            del self._entries[key]
            lock = self._locks.get(key)
            if lock is not None and not lock.locked():
                del self._locks[key]

    def clear(self) -> None:
        self._entries.clear()
