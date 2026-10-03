"""Queries on `categories`, `cuisines` and `tags`."""

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Cuisine, Tag
from app.repositories.search import contains


async def categories_in_order(session: AsyncSession) -> Sequence[Category]:
    """Every category, deleted ones included, by `sort_order`. A deleted category keeps its last
    one, so it comes after the category that took over its place; ties between deleted ones go
    by id (AGG-05)."""
    result = await session.execute(
        select(Category).order_by(
            Category.sort_order, Category.deleted_at.is_not(None), Category.id
        )
    )
    return result.scalars().all()


async def get_category(session: AsyncSession, category_id: str) -> Category | None:
    return await session.get(Category, category_id)


async def category_by_key(session: AsyncSession, key: str) -> Category | None:
    result = await session.execute(select(Category).where(Category.key == key))
    return result.scalar_one_or_none()


async def all_cuisines(session: AsyncSession) -> Sequence[Cuisine]:
    result = await session.execute(select(Cuisine))
    return result.scalars().all()


async def cuisine_by_name_norm(session: AsyncSession, name_norm: str) -> Cuisine | None:
    result = await session.execute(select(Cuisine).where(Cuisine.name_norm == name_norm))
    return result.scalar_one_or_none()


async def tags_matching(session: AsyncSession, query: str, limit: int) -> Sequence[Tag]:
    """Tags whose normalised name contains the normalised `query` (all if empty), prefix
    matches first."""
    statement = select(Tag)
    if query:
        matches, prefix = contains(Tag.name_norm, query)
        statement = statement.where(matches).order_by(prefix.is_(False))
    result = await session.execute(statement.order_by(Tag.name_norm).limit(limit))
    return result.scalars().all()


async def get_cuisine(session: AsyncSession, cuisine_id: str) -> Cuisine | None:
    return await session.get(Cuisine, cuisine_id)


async def cuisines_by_ids(
    session: AsyncSession, cuisine_ids: Iterable[str | None]
) -> dict[str, Cuisine]:
    ids = {cuisine_id for cuisine_id in cuisine_ids if cuisine_id is not None}
    if not ids:
        return {}
    result = await session.execute(select(Cuisine).where(Cuisine.id.in_(ids)))
    return {row.id: row for row in result.scalars()}


async def tags_by_name_norm(session: AsyncSession, names_norm: Iterable[str]) -> dict[str, Tag]:
    norms = set(names_norm)
    if not norms:
        return {}
    result = await session.execute(select(Tag).where(Tag.name_norm.in_(norms)))
    return {row.name_norm: row for row in result.scalars()}
