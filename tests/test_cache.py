from __future__ import annotations

import anyio
import pytest

from sportapi_mcp.cache import SnapshotCache

pytestmark = pytest.mark.anyio


async def test_reuses_snapshot_until_interval_passes() -> None:
    now = [0.0]
    cache = SnapshotCache(clock=lambda: now[0])
    calls = 0

    async def fetch() -> int:
        nonlocal calls
        calls += 1
        return calls

    assert await cache.get("k", 7, fetch) == (1, 0.0)
    now[0] = 6.5
    assert await cache.get("k", 7, fetch) == (1, 6.5)
    now[0] = 7.0
    assert await cache.get("k", 7, fetch) == (2, 0.0)
    assert await cache.get("other", 7, fetch) == (3, 0.0)


async def test_concurrent_calls_share_one_request() -> None:
    cache = SnapshotCache()
    calls = 0

    async def fetch() -> str:
        nonlocal calls
        calls += 1
        await anyio.sleep(0.05)
        return "snapshot"

    results: list[str] = []

    async def worker() -> None:
        value, _ = await cache.get("events", 7, fetch)
        results.append(value)

    async with anyio.create_task_group() as tg:
        for _ in range(5):
            tg.start_soon(worker)
    assert calls == 1 and results == ["snapshot"] * 5


async def test_failures_are_not_cached() -> None:
    cache = SnapshotCache()

    async def boom() -> int:
        raise RuntimeError("temporary")

    async def fine() -> int:
        return 1

    with pytest.raises(RuntimeError):
        await cache.get("k", 60, boom)
    assert await cache.get("k", 60, fine) == (1, 0.0)
