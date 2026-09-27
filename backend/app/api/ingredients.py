"""Ingredients, shared by everyone like a wiki (ING-01..06, NUT-02)."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.api.deps import CurrentUser, Db, Now, OffRefresh
from app.db.session import ReadSession, WriteSession
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.ingredients import (
    Ingredient,
    IngredientCreate,
    IngredientSummary,
    IngredientUpdate,
)
from app.schemas.products import Product
from app.services import ingredients, off_refresh

router = APIRouter(prefix="/api/ingredients", tags=["ingredients"], responses=ERROR_RESPONSES)


@router.get("")
async def list_ingredients(
    principal: CurrentUser,
    session: ReadSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    category_id: Annotated[str | None, Query(max_length=36)] = None,
) -> list[IngredientSummary]:
    """Search ignoring case, umlauts and accents (`q`), prefix matches first; without `q`,
    all ingredients by category order and name (at most 1000)."""
    return await ingredients.search(session, query=q, category_id=category_id)


@router.get("/similar")
async def list_similar_ingredients(
    principal: CurrentUser,
    session: ReadSession,
    name: Annotated[str, Query(max_length=100)],
) -> list[IngredientSummary]:
    """Up to five ingredients with a similar name, for the "similar ingredient exists" hint."""
    return await ingredients.similar(session, name)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ingredient(
    body: IngredientCreate, principal: CurrentUser, session: WriteSession, now: Now
) -> Ingredient:
    """Add an ingredient; the name must be unique ignoring case and umlauts."""
    return await ingredients.create_ingredient(session, principal, body, now=now)


@router.get("/{ingredient_id}")
async def get_ingredient(
    ingredient_id: str, principal: CurrentUser, session: ReadSession
) -> Ingredient:
    """An ingredient with its nutrition per nutrient and where each value comes from."""
    return await ingredients.get_ingredient(session, ingredient_id)


@router.patch("/{ingredient_id}")
async def update_ingredient(
    ingredient_id: str,
    body: IngredientUpdate,
    principal: CurrentUser,
    session: WriteSession,
    now: Now,
) -> Ingredient:
    """Change an ingredient (anyone may); the base unit is locked while products are linked."""
    return await ingredients.update_ingredient(session, principal, ingredient_id, body, now=now)


@router.get("/{ingredient_id}/products")
async def list_ingredient_products(
    ingredient_id: str,
    principal: CurrentUser,
    session: ReadSession,
    refresh: OffRefresh,
    database: Db,
    background: BackgroundTasks,
    now: Now,
) -> list[Product]:
    """The ingredient's products, by name and barcode; stale Open Food Facts products are
    refreshed after the response."""
    result = await ingredients.list_products(session, ingredient_id)
    off_refresh.schedule_if_stale(background, refresh, database, result, now=now)
    return result
