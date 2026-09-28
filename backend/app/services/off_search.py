"""Finding products on Open Food Facts by name (BAR-08, owner decision 2026-09-28).

Users start with no data and nothing to scan, so a product must also be findable by its name.
The app asks only on an explicit user action (a button or Enter, never as-you-type), and this
service keeps the traffic small:

- the query is trimmed and 2 to 80 characters long (422 otherwise, checked by the API);
- answers are cached per normalised query, page and name language for 24 hours in a small LRU
  (`SearchCache`, 200 entries, in memory: lost on restart, which only costs a request), so a
  repeated search does not ask Open Food Facts again; failures are not cached;
- Open Food Facts is asked outside any transaction under its own rate limit
  (`MEALMATE_OFF_SEARCH_PER_MINUTE`, see `app.integrations.off`): busy is 503 `off.busy`,
  slow or unreachable 503 `off.unavailable`.

Each product becomes a proposal exactly like a scanned one (`services.barcodes.proposal`);
products without a valid barcode are left out, as an ingredient from Open Food Facts is
refreshed by its barcode. Products whose barcode an ingredient already has are flagged
`in_mealmate`, so the user can pick that ingredient instead.
"""

import time
from collections import OrderedDict
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode
from app.core.ratelimit import Clock
from app.domain.text import normalize
from app.integrations.off import LOOKUP_MAX_WAIT_SECONDS, SEARCH_PAGE_SIZE, OffClient, OffProduct
from app.repositories import ingredients as ingredients_repo
from app.schemas.ingredients import OffSearchPage, OffSearchResult
from app.services import barcodes, ingredients
from app.services.principal import Principal

QUERY_MIN_LENGTH = 2
QUERY_MAX_LENGTH = 80
PAGE_MAX = 50
CACHE_SECONDS = 24 * 60 * 60
CACHE_ENTRIES = 200


@dataclass(frozen=True)
class SearchAnswer:
    """What Open Food Facts answered for one page: its products and how many match in all."""

    products: tuple[OffProduct, ...]
    count: int


type CacheKey = tuple[str, int, str]


class SearchCache:
    """Answers by (normalised query, page, language), kept for `max_age` seconds; the least
    recently used goes first once there are `max_entries`."""

    def __init__(
        self,
        *,
        max_entries: int = CACHE_ENTRIES,
        max_age: float = CACHE_SECONDS,
        clock: Clock = time.monotonic,
    ) -> None:
        self.max_entries = max_entries
        self.max_age = max_age
        self.clock = clock
        self._entries: OrderedDict[CacheKey, tuple[float, SearchAnswer]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, key: CacheKey) -> SearchAnswer | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        stored_at, answer = entry
        if self.clock() - stored_at >= self.max_age:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return answer

    def put(self, key: CacheKey, answer: SearchAnswer) -> None:
        self._entries[key] = (self.clock(), answer)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


async def _ask(off: OffClient, query: str, page: int, language: str) -> SearchAnswer:
    response = await off.search(
        query, page=page, language=language, max_wait=LOOKUP_MAX_WAIT_SECONDS
    )
    if response.status == "busy":
        raise ApiError(ErrorCode.OFF_BUSY, status_code=503)
    if response.status != "found":
        raise ApiError(ErrorCode.OFF_UNAVAILABLE, status_code=503)
    return SearchAnswer(response.results, response.count)


async def search(
    session: AsyncSession,
    off: OffClient,
    cache: SearchCache,
    principal: Principal,
    query: str,
    *,
    page: int,
) -> OffSearchPage:
    """One page of Open Food Facts products matching `query` (already trimmed and checked), as
    proposals named in the user's language, from the cache when possible."""
    async with session.begin():
        language = await barcodes.user_language(session, principal)
    key = (normalize(query), page, language)
    answer = cache.get(key)
    if answer is None:
        answer = await _ask(off, query, page, language)
        cache.put(key, answer)
    by_barcode: dict[str, OffProduct] = {}
    for product in answer.products:
        if product.code is not None:
            by_barcode.setdefault(product.code, product)  # the first of duplicates wins
    async with session.begin():
        known = await ingredients_repo.by_barcodes(session, by_barcode)
    results = [
        OffSearchResult(
            proposal=barcodes.proposal(product, barcode, language),
            in_mealmate=barcode in known,
            ingredient=ingredients.summary(known[barcode]) if barcode in known else None,
        )
        for barcode, product in by_barcode.items()
    ]
    return OffSearchPage(
        q=query,
        page=page,
        results=results,
        has_more=page < PAGE_MAX and page * SEARCH_PAGE_SIZE < answer.count,
    )
