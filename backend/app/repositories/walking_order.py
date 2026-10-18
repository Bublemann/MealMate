"""Queries on `walking_order_entries`."""

from collections.abc import Sequence

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.owners import OwnerKey
from app.models import Category, WalkingOrderEntry


def _owned_by(key: OwnerKey) -> ColumnElement[bool]:
    if key.couple_id is not None:
        return WalkingOrderEntry.couple_id == key.couple_id
    return WalkingOrderEntry.user_id == key.user_id


async def of_owner(
    session: AsyncSession, key: OwnerKey, *, without_deleted: bool = False
) -> Sequence[WalkingOrderEntry]:
    """The owner's own order, by position; empty while it follows the admins' order. With
    `without_deleted`, only the categories that aren't deleted."""
    query = (
        select(WalkingOrderEntry)
        .where(_owned_by(key))
        .order_by(WalkingOrderEntry.position, WalkingOrderEntry.category_id)
    )
    if without_deleted:
        query = query.join(Category, Category.id == WalkingOrderEntry.category_id).where(
            Category.deleted_at.is_(None)
        )
    result = await session.execute(query)
    return result.scalars().all()


async def owners_with(session: AsyncSession, category_id: str) -> list[OwnerKey]:
    """The owners whose own order holds the category."""
    result = await session.execute(
        select(WalkingOrderEntry.couple_id, WalkingOrderEntry.user_id).where(
            WalkingOrderEntry.category_id == category_id
        )
    )
    return [OwnerKey(couple_id, user_id) for couple_id, user_id in result.all()]


async def delete_of_owner(session: AsyncSession, key: OwnerKey) -> None:
    """Drop the owner's own order, so it follows the admins' one again."""
    await session.execute(delete(WalkingOrderEntry).where(_owned_by(key)))


async def not_deleted_counts(session: AsyncSession) -> dict[OwnerKey, int]:
    """Every own order, with how many categories that aren't deleted it holds."""
    result = await session.execute(
        select(WalkingOrderEntry.couple_id, WalkingOrderEntry.user_id, func.count())
        .join(Category, Category.id == WalkingOrderEntry.category_id)
        .where(Category.deleted_at.is_(None))
        .group_by(WalkingOrderEntry.couple_id, WalkingOrderEntry.user_id)
    )
    return {OwnerKey(couple_id, user_id): count for couple_id, user_id, count in result.all()}
