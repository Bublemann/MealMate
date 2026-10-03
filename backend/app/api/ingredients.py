"""Ingredients, shared by everyone like a wiki (ING-01..06, NUT-02), with their barcode and Open
Food Facts data: the barcode lookup (BAR-02, BAR-03), the name search (BAR-08) and pending
updates (BAR-06)."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status
from pydantic import StringConstraints

from app.api.deps import CurrentUser, Db, Now, OffRefresh, OffSearchCache
from app.db.session import ReadSession, WriteSession
from app.domain.catalog import BARCODE_INPUT_MAX_LENGTH, BRAND_MAX_LENGTH
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.ingredients import (
    BarcodeLookup,
    Ingredient,
    IngredientBarcodeLink,
    IngredientCreate,
    IngredientSummary,
    IngredientUpdate,
    OffSearchPage,
)
from app.services import barcodes, ingredients, off_refresh, off_search

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"], responses=ERROR_RESPONSES)

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
async def list_ingredients(
    principal: CurrentUser,
    session: ReadSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category_id: Annotated[list[CategoryId] | None, Query(max_length=100)] = None,
) -> list[IngredientSummary]:
    """Search name and brand ignoring case, umlauts and accents (`q`): an exact name first,
    then names starting with `q`, then the rest, each in dictionary order by name and brand
    (Ä sorts as A); without `q`, all ingredients in that order (at most 1000). `category_id`
    is repeatable: an ingredient matches if it is in any of the given categories."""
    return await ingredients.search(session, query=q, category_ids=category_id or [])


@router.get("/similar")
async def list_similar_ingredients(
    principal: CurrentUser,
    session: ReadSession,
    name: Annotated[str, Query(max_length=100)],
    brand: Annotated[str | None, Query(max_length=BRAND_MAX_LENGTH)] = None,
) -> list[IngredientSummary]:
    """Up to five ingredients with a similar name, for the "similar ingredient exists" hint
    (only a hint: names need not be unique); those with the same name and `brand` first."""
    return await ingredients.similar(session, name, brand)


@router.get("/lookup")
async def lookup_barcode(
    principal: CurrentUser,
    session: ReadSession,
    refresh: OffRefresh,
    database: Db,
    background: BackgroundTasks,
    now: Now,
    barcode: Annotated[str, Query(max_length=BARCODE_INPUT_MAX_LENGTH)],
    own_only: bool = False,
) -> BarcodeLookup:
    """Look a scanned or typed barcode up: our own ingredients first, then Open Food Facts (a
    proposal, not saved). With `own_only`, only our own ingredients: `none` then means that
    no ingredient has the barcode, and Open Food Facts isn't asked. 422 `invalid_format` for a
    barcode with a wrong check digit, 503 `off.busy` while too many lookups wait for Open
    Food Facts. A stale ingredient from Open Food Facts is refreshed after the response."""
    result = await barcodes.lookup(session, refresh.off, principal, barcode, own_only=own_only)
    if result.ingredient is not None:
        off_refresh.schedule_if_stale(background, refresh, database, [result.ingredient], now=now)
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
async def create_ingredient(
    body: IngredientCreate, principal: CurrentUser, session: WriteSession, now: Now
) -> Ingredient:
    """Add an ingredient, by hand or from an Open Food Facts proposal (`off`) in one request;
    409 `ingredient.barcode_taken` if another ingredient has the barcode."""
    return await ingredients.create_ingredient(session, principal, body, now=now)


@router.get("/{ingredient_id}")
async def get_ingredient(
    ingredient_id: str,
    principal: CurrentUser,
    session: ReadSession,
    refresh: OffRefresh,
    database: Db,
    background: BackgroundTasks,
    now: Now,
) -> Ingredient:
    """An ingredient with its values, barcode, Open Food Facts data and usage; a stale one from
    Open Food Facts is refreshed after the response."""
    result = await ingredients.get_ingredient(session, ingredient_id)
    off_refresh.schedule_if_stale(background, refresh, database, [result], now=now)
    return result


@router.patch("/{ingredient_id}")
async def update_ingredient(
    ingredient_id: str,
    body: IngredientUpdate,
    principal: CurrentUser,
    session: WriteSession,
    now: Now,
) -> Ingredient:
    """Change an ingredient (anyone may); Open Food Facts fields sent become user-edited.
    Clearing or changing the barcode of one from Open Food Facts makes it manual. 409
    `ingredient.unit_mismatch` with the number of meals and drafts affected when a base-unit
    change would leave amounts not fitting, unless `accept_unit_mismatch` is true (D-33)."""
    return await ingredients.update_ingredient(session, principal, ingredient_id, body, now=now)


@router.post("/{ingredient_id}/barcode")
async def link_barcode(
    ingredient_id: str,
    body: IngredientBarcodeLink,
    principal: CurrentUser,
    session: WriteSession,
    now: Now,
) -> Ingredient:
    """Give an ingredient without a barcode a scanned one (the scanner's "already in
    MealMate"); it never replaces one: 409 `ingredient.has_barcode` if it has a barcode, 409
    `ingredient.barcode_taken` if another ingredient has this one. The edit form changes a
    barcode with PATCH instead."""
    return await ingredients.link_barcode(session, principal, ingredient_id, body, now=now)


@router.post("/{ingredient_id}/pending-update/apply")
async def apply_pending_update(
    ingredient_id: str, principal: CurrentUser, session: WriteSession, now: Now
) -> Ingredient:
    """Take the newer Open Food Facts values (BAR-06); those fields are no longer
    user-edited. 409 `ingredient.no_pending_update` if there are none."""
    return await ingredients.apply_pending_update(session, principal, ingredient_id, now=now)


@router.post("/{ingredient_id}/pending-update/ignore")
async def ignore_pending_update(
    ingredient_id: str, principal: CurrentUser, session: WriteSession, now: Now
) -> Ingredient:
    """Keep the user's values (BAR-06); the same Open Food Facts version is not proposed
    again. 409 `ingredient.no_pending_update` if there is nothing to ignore."""
    return await ingredients.ignore_pending_update(session, principal, ingredient_id, now=now)
