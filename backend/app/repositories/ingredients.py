"""Queries on `ingredients`."""

from collections.abc import Iterable, Sequence

from sqlalchemy import ScalarSelect, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Ingredient, Product
from app.repositories.search import contains


def _product_count() -> ScalarSelect[int]:
    return (
        select(func.count(Product.id))
        .where(Product.ingredient_id == Ingredient.id)
        .correlate(Ingredient)
        .scalar_subquery()
    )


async def get(session: AsyncSession, ingredient_id: str) -> Ingredient | None:
    return await session.get(Ingredient, ingredient_id)


async def name_taken(
    session: AsyncSession, name_norm: str, *, except_id: str | None = None
) -> bool:
    query = select(Ingredient.id).where(Ingredient.name_norm == name_norm)
    if except_id is not None:
        query = query.where(Ingredient.id != except_id)
    return (await session.execute(query)).first() is not None


async def search(
    session: AsyncSession, *, query: str, category_id: str | None, limit: int
) -> Sequence[tuple[Ingredient, int]]:
    """Ingredients with their product counts. With a normalised `query`, those whose
    normalised name contains it (also with umlaut spellings folded, so "apfel" finds "Äpfel"),
    prefix matches first, then by name; without one, all of them by category order and name."""
    statement = select(Ingredient, _product_count())
    if category_id is not None:
        statement = statement.where(Ingredient.category_id == category_id)
    if query:
        matches, prefix = contains(Ingredient.name_norm, query)
        statement = statement.where(matches).order_by(
            prefix.is_(False), Ingredient.name_norm, Ingredient.id
        )
    else:
        statement = statement.join(Category, Category.id == Ingredient.category_id).order_by(
            Category.sort_order, Ingredient.name_norm, Ingredient.id
        )
    result = await session.execute(statement.limit(limit))
    return [(row[0], row[1]) for row in result]


async def names(session: AsyncSession) -> list[tuple[str, str]]:
    """`(id, name_norm)` of every ingredient."""
    result = await session.execute(select(Ingredient.id, Ingredient.name_norm))
    return [(row[0], row[1]) for row in result]


async def with_product_counts(
    session: AsyncSession, ingredient_ids: Iterable[str]
) -> dict[str, tuple[Ingredient, int]]:
    ids = set(ingredient_ids)
    if not ids:
        return {}
    result = await session.execute(
        select(Ingredient, _product_count()).where(Ingredient.id.in_(ids))
    )
    return {row[0].id: (row[0], row[1]) for row in result}


async def by_ids(session: AsyncSession, ingredient_ids: Iterable[str]) -> dict[str, Ingredient]:
    ids = set(ingredient_ids)
    if not ids:
        return {}
    result = await session.execute(select(Ingredient).where(Ingredient.id.in_(ids)))
    return {row.id: row for row in result.scalars()}
