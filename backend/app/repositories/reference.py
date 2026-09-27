"""Queries on `categories`, `cuisines` and `tags`."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Cuisine, Tag
from app.repositories.search import contains


async def categories_in_order(session: AsyncSession) -> Sequence[Category]:
    result = await session.execute(select(Category).order_by(Category.sort_order, Category.key))
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
