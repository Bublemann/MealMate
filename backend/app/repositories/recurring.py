"""Queries on `recurring_items`."""

from collections.abc import Collection, Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.owners import OwnerKey
from app.models import Ingredient, RecurringItem


def _owned_by(key: OwnerKey) -> ColumnElement[bool]:
    if key.couple_id is not None:
        return RecurringItem.couple_id == key.couple_id
    return RecurringItem.user_id == key.user_id


async def get(session: AsyncSession, item_id: str) -> RecurringItem | None:
    return await session.get(RecurringItem, item_id)


async def of_owner(
    session: AsyncSession, key: OwnerKey
) -> Sequence[tuple[RecurringItem, Ingredient]]:
    """The owner's set with each item's ingredient, in dictionary order by name and brand."""
    result = await session.execute(
        select(RecurringItem, Ingredient)
        .join(Ingredient, Ingredient.id == RecurringItem.ingredient_id)
        .where(_owned_by(key))
        .order_by(Ingredient.name_sort, func.coalesce(Ingredient.brand_sort, ""), Ingredient.id)
    )
    return result.all()


async def in_set(session: AsyncSession, key: OwnerKey, ingredient_id: str) -> RecurringItem | None:
    """The owner's item of that ingredient, if the set has one."""
    result = await session.execute(
        select(RecurringItem).where(_owned_by(key), RecurringItem.ingredient_id == ingredient_id)
    )
    return result.scalar_one_or_none()


async def of_users(session: AsyncSession, user_ids: Collection[str]) -> Sequence[RecurringItem]:
    """The users' own items (not their couple's), oldest first."""
    result = await session.execute(
        select(RecurringItem)
        .where(RecurringItem.user_id.in_(user_ids))
        .order_by(RecurringItem.created_at, RecurringItem.id)
    )
    return result.scalars().all()


async def of_couple(session: AsyncSession, couple_id: str) -> Sequence[RecurringItem]:
    """The couple's items, oldest first."""
    result = await session.execute(
        select(RecurringItem)
        .where(RecurringItem.couple_id == couple_id)
        .order_by(RecurringItem.created_at, RecurringItem.id)
    )
    return result.scalars().all()


async def with_ingredient(session: AsyncSession, ingredient_id: str) -> Sequence[RecurringItem]:
    """Every set's item of that ingredient, oldest first."""
    result = await session.execute(
        select(RecurringItem)
        .where(RecurringItem.ingredient_id == ingredient_id)
        .order_by(RecurringItem.created_at, RecurringItem.id)
    )
    return result.scalars().all()
