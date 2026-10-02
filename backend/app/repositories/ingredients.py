"""Queries on `ingredients`."""

from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.text import fold_umlauts
from app.models import Ingredient
from app.repositories.search import contains, folded


async def get(session: AsyncSession, ingredient_id: str) -> Ingredient | None:
    return await session.get(Ingredient, ingredient_id)


async def by_barcode(session: AsyncSession, barcode: str) -> Ingredient | None:
    result = await session.execute(select(Ingredient).where(Ingredient.barcode == barcode))
    return result.scalar_one_or_none()


async def by_barcodes(session: AsyncSession, barcodes: Iterable[str]) -> dict[str, Ingredient]:
    """The ingredients with these barcodes, by barcode."""
    codes = set(barcodes)
    if not codes:
        return {}
    result = await session.execute(select(Ingredient).where(Ingredient.barcode.in_(codes)))
    return {str(row.barcode): row for row in result.scalars()}


async def barcode_owner(
    session: AsyncSession, barcode: str, *, except_id: str | None = None
) -> str | None:
    """The id of the ingredient with this barcode (other than `except_id`), if any."""
    query = select(Ingredient.id).where(Ingredient.barcode == barcode)
    if except_id is not None:
        query = query.where(Ingredient.id != except_id)
    return (await session.execute(query)).scalar_one_or_none()


def _label_norm() -> ColumnElement[str]:
    """`name brand` normalised, so that "milch weihen" finds "Milch (Weihenstephan)"."""
    return Ingredient.name_norm + " " + func.coalesce(Ingredient.brand_norm, "")


async def search(
    session: AsyncSession, *, query: str, category_id: str | None, limit: int
) -> Sequence[Ingredient]:
    """With a normalised `query`: the ingredients whose normalised name or brand, or both
    together ("name brand"), contain it (also with umlaut spellings folded, so "apfel" finds
    "Äpfel"); an exact name first, then names starting with it, each in dictionary order by
    name and brand. Without one: all of them in that order."""
    statement = select(Ingredient)
    if category_id is not None:
        statement = statement.where(Ingredient.category_id == category_id)
    order = (Ingredient.name_sort, func.coalesce(Ingredient.brand_sort, ""), Ingredient.id)
    if query:
        # The label holds the name and the brand, so it matches either or both.
        matches, _ = contains(_label_norm(), query)
        _, prefix = contains(Ingredient.name_norm, query)
        exact = or_(
            Ingredient.name_norm == query, folded(Ingredient.name_norm) == fold_umlauts(query)
        )
        statement = statement.where(matches).order_by(exact.is_(False), prefix.is_(False), *order)
    else:
        statement = statement.order_by(*order)
    result = await session.execute(statement.limit(limit))
    return result.scalars().all()


async def names(session: AsyncSession) -> list[tuple[str, str]]:
    """`(id, name_norm)` of every ingredient."""
    result = await session.execute(select(Ingredient.id, Ingredient.name_norm))
    return [(row[0], row[1]) for row in result]


async def by_ids(session: AsyncSession, ingredient_ids: Iterable[str]) -> dict[str, Ingredient]:
    ids = set(ingredient_ids)
    if not ids:
        return {}
    result = await session.execute(select(Ingredient).where(Ingredient.id.in_(ids)))
    return {row.id: row for row in result.scalars()}


async def stale_from_off(
    session: AsyncSession, fetched_before: datetime, *, limit: int | None = None
) -> list[str]:
    """The ids of the ingredients from Open Food Facts fetched before `fetched_before` (or
    never), the longest ago first; at most `limit` (None: all)."""
    result = await session.execute(
        select(Ingredient.id)
        .where(
            Ingredient.source == "off",
            Ingredient.barcode.is_not(None),
            or_(Ingredient.fetched_at.is_(None), Ingredient.fetched_at < fetched_before),
        )
        .order_by(Ingredient.fetched_at.asc().nulls_first(), Ingredient.id)
        .limit(limit)
    )
    return list(result.scalars())
