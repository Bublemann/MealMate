"""Queries on `recurring_items`."""

from collections.abc import Collection, Sequence

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.owners import OwnerKey
from app.models import Item, ListHiddenDueItem, RecurringItem


def _owned_by(key: OwnerKey) -> ColumnElement[bool]:
    if key.couple_id is not None:
        return RecurringItem.couple_id == key.couple_id
    return RecurringItem.user_id == key.user_id


async def get(session: AsyncSession, recurring_id: str) -> RecurringItem | None:
    return await session.get(RecurringItem, recurring_id)


async def of_owner(
    session: AsyncSession, key: OwnerKey, *, not_hidden_on: str | None = None
) -> Sequence[tuple[RecurringItem, Item]]:
    """The owner's set with each recurring item's item, in dictionary order by name and brand;
    without the items hidden on the list `not_hidden_on` (LIST-16), if given."""
    query = (
        select(RecurringItem, Item)
        .join(Item, Item.id == RecurringItem.item_id)
        .where(_owned_by(key))
        .order_by(Item.name_sort, func.coalesce(Item.brand_sort, ""), Item.id)
    )
    if not_hidden_on is not None:
        query = query.where(
            ~exists().where(
                ListHiddenDueItem.list_id == not_hidden_on,
                ListHiddenDueItem.item_id == RecurringItem.item_id,
            )
        )
    result = await session.execute(query)
    return result.all()


async def in_set(session: AsyncSession, key: OwnerKey, item_id: str) -> RecurringItem | None:
    """The owner's recurring item of that item, if the set has one."""
    result = await session.execute(
        select(RecurringItem).where(_owned_by(key), RecurringItem.item_id == item_id)
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


async def with_item(session: AsyncSession, item_id: str) -> Sequence[RecurringItem]:
    """Every set's recurring item of that item, oldest first."""
    result = await session.execute(
        select(RecurringItem)
        .where(RecurringItem.item_id == item_id)
        .order_by(RecurringItem.created_at, RecurringItem.id)
    )
    return result.scalars().all()
