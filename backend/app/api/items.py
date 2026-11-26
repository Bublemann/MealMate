"""Items, shared by everyone like a wiki (ING-01..06, NUT-02), with their barcode and Open
Food Facts data: the barcode lookup (BAR-02, BAR-03), the name search (BAR-08) and pending
updates (BAR-06)."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status
from pydantic import StringConstraints

from app.api.deps import CurrentUser, Db, Now, OffRefresh, OffSearchCache
from app.db.session import ReadSession, WriteSession
from app.domain.catalog import BARCODE_INPUT_MAX_LENGTH, BRAND_MAX_LENGTH
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.items import (
    BarcodeLookup,
    Item,
    ItemBarcodeLink,
    ItemCreate,
    ItemKind,
    ItemSearchResult,
    ItemSummary,
    ItemUpdate,
    OffSearchPage,
)
from app.services import barcodes, items, off_refresh, off_search

router = APIRouter(prefix="/api/items", tags=["items"], responses=ERROR_RESPONSES)

OffSearchQuery = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=off_search.QUERY_MIN_LENGTH,
        max_length=off_search.QUERY_MAX_LENGTH,
    ),
    Query(),
]

# A category id (a UUID). The list takes up to 100 of them; the seed has 17 categories.
CategoryId = Annotated[str, StringConstraints(max_length=36)]


@router.get("")
async def list_items(
    principal: CurrentUser,
    session: ReadSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category_id: Annotated[list[CategoryId] | None, Query(max_length=100)] = None,
    kind: Annotated[ItemKind | None, Query()] = None,
) -> list[ItemSearchResult]:
    """Search name and brand ignoring case, umlauts and accents (`q`): an exact name first,
    then names starting with `q`, then the rest, each in dictionary order by name and brand
    (Ä sorts as A); `exact` marks the exact names, whatever their brand. Without `q`, all
    items in that order (at most 1000). `category_id`
    is repeatable: an item matches if it is in any of the given categories. With `kind`, only
    food or only supplies (the meal form's search asks for food, D-55)."""
    return await items.search(session, query=q, category_ids=category_id or [], kind=kind)


@router.get("/similar")
async def list_similar_items(
    principal: CurrentUser,
    session: ReadSession,
    name: Annotated[str, Query(max_length=100)],
    brand: Annotated[str | None, Query(max_length=BRAND_MAX_LENGTH)] = None,
) -> list[ItemSummary]:
    """Up to five items with a similar name, for the "similar item exists" hint
    (only a hint: names need not be unique); those with the same name and `brand` first."""
    return await items.similar(session, name, brand)


@router.get("/lookup")
async def lookup_barcode(
    principal: CurrentUser,
    session: ReadSession,
    refresh: OffRefresh,
    database: Db,
    background: BackgroundTasks,
    now: Now,
    barcode: Annotated[str, Query(max_length=BARCODE_INPUT_MAX_LENGTH)],
    own_only: Annotated[bool, Query()] = False,
) -> BarcodeLookup:
    """Look a scanned or typed barcode up: our own items first, then Open Food Facts (a
    proposal, not saved). With `own_only`, only our own items: `none` then means that
    no item has the barcode, and Open Food Facts isn't asked. 422 `invalid_format` for a
    barcode with a wrong check digit, 503 `off.busy` while too many lookups wait for Open
    Food Facts. A stale item from Open Food Facts is refreshed after the response."""
    result = await barcodes.lookup(session, refresh.off, principal, barcode, own_only=own_only)
    if result.item is not None:
        off_refresh.schedule_if_stale(background, refresh, database, [result.item], now=now)
    return result


@router.get("/off-search")
async def search_open_food_facts(
    principal: CurrentUser,
    session: ReadSession,
    refresh: OffRefresh,
    cache: OffSearchCache,
    q: OffSearchQuery,
    page: Annotated[int, Query(ge=1, le=off_search.PAGE_MAX)] = 1,
) -> OffSearchPage:
    """Search Open Food Facts by name, for an explicit user action only (a button or Enter,
    never while typing; BAR-08): one page of up to 20 products sold in Germany, as proposals
    like the barcode lookup's, those already in MealMate flagged. `q` is trimmed and must be 2
    to 80 characters long. Answers are cached for 24 hours; 503 `off.busy` while too many
    searches wait for Open Food Facts, 503 `off.unavailable` when it is slow or unreachable."""
    return await off_search.search(session, refresh.off, cache, principal, q, page=page)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate, principal: CurrentUser, session: WriteSession, now: Now
) -> Item:
    """Add an item, by hand or from an Open Food Facts proposal (`off`) in one request;
    409 `item.barcode_taken` if another item has the barcode."""
    return await items.create_item(session, principal, body, now=now)


@router.get("/{item_id}")
async def get_item(
    item_id: str,
    principal: CurrentUser,
    session: ReadSession,
    refresh: OffRefresh,
    database: Db,
    background: BackgroundTasks,
    now: Now,
) -> Item:
    """An item with its values, barcode, Open Food Facts data and usage; a stale one from
    Open Food Facts is refreshed after the response."""
    result = await items.get_item(session, item_id)
    off_refresh.schedule_if_stale(background, refresh, database, [result], now=now)
    return result


@router.patch("/{item_id}")
async def update_item(
    item_id: str,
    body: ItemUpdate,
    principal: CurrentUser,
    session: WriteSession,
    now: Now,
) -> Item:
    """Change an item (anyone may); Open Food Facts fields sent become user-edited.
    Clearing or changing the barcode of one from Open Food Facts makes it manual. 409
    `item.unit_mismatch` with the number of meals and drafts affected when a base-unit
    change would leave amounts not fitting, unless `accept_unit_mismatch` is true (D-33)."""
    return await items.update_item(session, principal, item_id, body, now=now)


@router.post("/{item_id}/barcode")
async def link_barcode(
    item_id: str,
    body: ItemBarcodeLink,
    principal: CurrentUser,
    session: WriteSession,
    now: Now,
) -> Item:
    """Give an item without a barcode a scanned one (the scanner's "already in
    MealMate"); it never replaces one: 409 `item.has_barcode` if it has a barcode, 409
    `item.barcode_taken` if another item has this one. The edit form changes a
    barcode with PATCH instead."""
    return await items.link_barcode(session, principal, item_id, body, now=now)


@router.post("/{item_id}/pending-update/apply")
async def apply_pending_update(
    item_id: str, principal: CurrentUser, session: WriteSession, now: Now
) -> Item:
    """Take the newer Open Food Facts values (BAR-06); those fields are no longer
    user-edited. 409 `item.no_pending_update` if there are none."""
    return await items.apply_pending_update(session, principal, item_id, now=now)


@router.post("/{item_id}/pending-update/ignore")
async def ignore_pending_update(
    item_id: str, principal: CurrentUser, session: WriteSession, now: Now
) -> Item:
    """Keep the user's values (BAR-06); the same Open Food Facts version is not proposed
    again. 409 `item.no_pending_update` if there is nothing to ignore."""
    return await items.ignore_pending_update(session, principal, item_id, now=now)
