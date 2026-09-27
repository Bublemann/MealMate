"""The cache of list responses: builds for the same entry at once share one (PERF-02); a build
that fails or is cancelled leaves the others to build their own."""

import asyncio

import pytest

from app.services.list_cache import CacheKey, ListCache

KEY: CacheKey = ("list", "viewer", 3600)


class Builds:
    """A build that waits until the test lets it finish, and counts how often it ran; the first
    `failures` ones fail."""

    def __init__(self, failures: int = 0) -> None:
        self.count = 0
        self.failures = failures
        self.release = asyncio.Event()
        self.counted = asyncio.Condition()

    async def __call__(self) -> bytes:
        async with self.counted:
            self.count += 1
            number = self.count
            self.counted.notify_all()
        await self.release.wait()
        if number <= self.failures:
            raise RuntimeError("database gone")
        return f"body {number}".encode()


async def started(builds: Builds, count: int) -> None:
    async with builds.counted:
        await builds.counted.wait_for(lambda: builds.count >= count)


async def test_requests_at_once_share_one_build() -> None:
    cache, builds = ListCache(), Builds()
    first = asyncio.create_task(cache.get_or_build(KEY, 1, builds))
    await started(builds, 1)
    others = [asyncio.create_task(cache.get_or_build(KEY, 1, builds)) for _ in range(3)]
    # A write meanwhile: a request of the new generation does not take the old build.
    newer = asyncio.create_task(cache.get_or_build(KEY, 2, builds))
    await started(builds, 2)

    builds.release.set()
    entries = await asyncio.gather(first, *others)

    assert {entry.body for entry in entries} == {b"body 1"}
    assert (await newer).body == b"body 2"
    assert builds.count == 2


async def test_a_failed_build_leaves_the_others_to_build_their_own() -> None:
    cache, builds = ListCache(), Builds(failures=1)
    first = asyncio.create_task(cache.get_or_build(KEY, 1, builds))
    await started(builds, 1)
    waiting = asyncio.create_task(cache.get_or_build(KEY, 1, builds))
    await asyncio.sleep(0)

    builds.release.set()
    with pytest.raises(RuntimeError):
        await first

    assert (await waiting).body == b"body 2"
    assert cache.get(KEY, 1) is not None


async def test_a_cancelled_request_does_not_cancel_the_build() -> None:
    cache, builds = ListCache(), Builds()
    first = asyncio.create_task(cache.get_or_build(KEY, 1, builds))
    await started(builds, 1)
    waiting = asyncio.create_task(cache.get_or_build(KEY, 1, builds))
    await asyncio.sleep(0)

    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    builds.release.set()

    assert (await first).body == b"body 1"
    assert builds.count == 1
