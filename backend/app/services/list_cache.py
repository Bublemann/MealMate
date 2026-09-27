"""The responses of `GET /api/lists/{id}` for polling (SYNC-08, PERF-02).

Every phone on a list's screen asks for it every 5 seconds; building the answer takes the
content queries and the aggregation, while nearly every poll ends in a 304. So the finished
body and its ETag are kept per list, viewer and media URL hour (signed photo URLs change with
the hour), and served again while both hold:

- no write transaction was committed in this process since (`Database.write_generation`),
  whatever it changed: any write may change what a viewer sees (a meal, a privacy switch, a
  couple), and writes are rare next to polls;
- the entry is younger than `TTL_SECONDS`, which bounds how long a write from another process
  (a CLI command) can go unseen.

At most `MAX_ENTRIES` are kept, the least recently used ones go first. The viewer is part of
the key, so two viewers never share an entry. Access is checked before the cache is asked
(the caller authenticates as usual); a list the viewer may not see is never stored.

Phones poll at the same moments (all of them right after a change), so requests for an entry
that is being built wait for that build instead of building it again; if it fails, each builds
its own.
"""

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.core import etags

type Clock = Callable[[], float]
# List id, viewer id, expiry of the media URLs in the body (`app.media.urls.expiry`).
type CacheKey = tuple[str, str, int]

TTL_SECONDS = 60.0
MAX_ENTRIES = 512


@dataclass(frozen=True)
class CachedList:
    """A list's response body as one viewer got it, with its weak ETag. `generation` and
    `created_at` (monotonic seconds) are those from before it was read."""

    generation: int
    created_at: float
    etag: str
    body: bytes

    @property
    def headers(self) -> dict[str, str]:
        return {"ETag": self.etag, "Cache-Control": "no-cache"}


@dataclass
class ListCache:
    clock: Clock = time.monotonic
    ttl: float = TTL_SECONDS
    max_entries: int = MAX_ENTRIES
    _entries: OrderedDict[CacheKey, CachedList] = field(default_factory=OrderedDict, repr=False)
    # The builds under way: their generation and the entry they will give.
    _building: dict[CacheKey, tuple[int, asyncio.Future[CachedList]]] = field(
        default_factory=dict, repr=False
    )

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: CacheKey, generation: int) -> CachedList | None:
        """The entry, if nothing was written since and it is not too old."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.generation != generation or self.clock() - entry.created_at >= self.ttl:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return entry

    async def get_or_build(
        self, key: CacheKey, generation: int, build: Callable[[], Awaitable[bytes]]
    ) -> CachedList:
        """The entry, or a new one from `build()` (which reads the database). `generation`
        must be read before `build()` starts reading, so a write committed meanwhile makes the
        new entry stale at once."""
        if (entry := self.get(key, generation)) is not None:
            return entry
        if (building := self._building.get(key)) is not None and building[0] == generation:
            try:
                return await asyncio.shield(building[1])
            except asyncio.CancelledError:
                if not building[1].cancelled():
                    raise  # this request was cancelled, not the build
        future: asyncio.Future[CachedList] = asyncio.get_running_loop().create_future()
        self._building[key] = (generation, future)
        try:
            created_at = self.clock()
            body = await build()
        except BaseException:
            future.cancel()  # those waiting build their own
            raise
        finally:
            if self._building.get(key, (0, None))[1] is future:
                del self._building[key]
        entry = CachedList(generation, created_at, etags.weak_etag(body), body)
        self._entries[key] = entry
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
        future.set_result(entry)
        return entry
