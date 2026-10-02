"""Queries on `shopping_lists`, `list_meals`, `list_meal_ingredients`, `list_extra_items` and
`list_line_states`.

The content of lists (meals, frozen rows, extra items, line states) is loaded in batches per
list id, so reading a list or many summaries takes a fixed number of queries (PERF).
"""

from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from datetime import datetime

from sqlalchemy import Subquery, and_, delete, func, or_, select, union, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lists import FeedPosition, ListStatus
from app.models import (
    ListExtraItem,
    ListLineState,
    ListMeal,
    ListMealIngredient,
    Meal,
    MealIngredient,
    ProcessedOp,
    ShoppingList,
)


async def get(session: AsyncSession, list_id: str) -> ShoppingList | None:
    return await session.get(ShoppingList, list_id)


async def mine(
    session: AsyncSession, user_id: str, partner_id: str | None, statuses: Collection[ListStatus]
) -> Sequence[ShoppingList]:
    """The user's own lists and those their partner shares with them, most recently edited
    first."""
    condition = ShoppingList.owner_id == user_id
    if partner_id is not None:
        condition = or_(
            condition,
            (ShoppingList.owner_id == partner_id) & ShoppingList.shared_with_partner.is_(True),
        )
    result = await session.execute(
        select(ShoppingList)
        .where(condition, ShoppingList.status.in_(statuses))
        .order_by(ShoppingList.updated_at.desc(), ShoppingList.id.desc())
    )
    return result.scalars().all()


async def feed(
    session: AsyncSession,
    owner_ids: Collection[str],
    statuses: Collection[str],
    after: FeedPosition | None,
    limit: int,
) -> Sequence[ShoppingList]:
    """At most `limit` lists of the given owners in the given states, in the order of the list
    feed (UI-02): newest created first, ties by id; only those after `after` if given."""
    statement = select(ShoppingList).where(
        ShoppingList.owner_id.in_(owner_ids), ShoppingList.status.in_(statuses)
    )
    if after is not None:
        statement = statement.where(
            or_(
                ShoppingList.created_at < after.created_at,
                and_(ShoppingList.created_at == after.created_at, ShoppingList.id < after.list_id),
            )
        )
    result = await session.execute(
        statement.order_by(ShoppingList.created_at.desc(), ShoppingList.id.desc()).limit(limit)
    )
    return result.scalars().all()


async def bump(session: AsyncSession, list_ids: Iterable[str], now: datetime) -> None:
    """Record a change of the lists: `version = version + 1` in SQL, so concurrent changes
    are never lost, and `updated_at` (plan § 5.7)."""
    ids = set(list_ids)
    if ids:
        await session.execute(
            update(ShoppingList)
            .where(ShoppingList.id.in_(ids))
            .values(version=ShoppingList.version + 1, updated_at=now)
            .execution_options(synchronize_session="fetch")
        )


# --- list meals -------------------------------------------------------------------------------


async def meals_for(session: AsyncSession, list_ids: Iterable[str]) -> dict[str, list[ListMeal]]:
    """The list meals per list id, in the order they were added."""
    ids = set(list_ids)
    meals: dict[str, list[ListMeal]] = defaultdict(list)
    if ids:
        result = await session.execute(
            select(ListMeal)
            .where(ListMeal.list_id.in_(ids))
            .order_by(ListMeal.list_id, ListMeal.position, ListMeal.id)
        )
        for row in result.scalars():
            meals[row.list_id].append(row)
    return meals


async def get_meal(session: AsyncSession, list_id: str, list_meal_id: str) -> ListMeal | None:
    row = await session.get(ListMeal, list_meal_id)
    return row if row is not None and row.list_id == list_id else None


async def meal_on_list(session: AsyncSession, list_id: str, meal_id: str) -> ListMeal | None:
    result = await session.execute(
        select(ListMeal).where(ListMeal.list_id == list_id, ListMeal.meal_id == meal_id)
    )
    return result.scalar_one_or_none()


async def next_meal_position(session: AsyncSession, list_id: str) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(ListMeal.position) + 1, 0)).where(ListMeal.list_id == list_id)
    )
    return int(result.scalar_one())


async def frozen_rows_for(
    session: AsyncSession, list_meal_ids: Iterable[str]
) -> dict[str, list[ListMealIngredient]]:
    """The frozen rows per list meal id, by position."""
    ids = set(list_meal_ids)
    rows: dict[str, list[ListMealIngredient]] = defaultdict(list)
    if ids:
        result = await session.execute(
            select(ListMealIngredient)
            .where(ListMealIngredient.list_meal_id.in_(ids))
            .order_by(ListMealIngredient.list_meal_id, ListMealIngredient.position)
        )
        for row in result.scalars():
            rows[row.list_meal_id].append(row)
    return rows


async def live_meals_of_meal(session: AsyncSession, meal_id: str) -> Sequence[ListMeal]:
    """The not yet frozen list meals of a meal, on any list."""
    result = await session.execute(
        select(ListMeal).where(ListMeal.meal_id == meal_id, ListMeal.frozen_at.is_(None))
    )
    return result.scalars().all()


async def live_meals_of_owner(
    session: AsyncSession,
    meal_owner_id: str,
    *,
    list_owner_ids: Collection[str] | None = None,
    except_list_owner_ids: Collection[str] = (),
) -> Sequence[ListMeal]:
    """The not yet frozen list meals whose meal belongs to `meal_owner_id`, on lists of the
    given owners (all owners if None) other than `except_list_owner_ids`."""
    statement = (
        select(ListMeal)
        .join(Meal, Meal.id == ListMeal.meal_id)
        .join(ShoppingList, ShoppingList.id == ListMeal.list_id)
        .where(Meal.owner_id == meal_owner_id, ListMeal.frozen_at.is_(None))
    )
    if list_owner_ids is not None:
        statement = statement.where(ShoppingList.owner_id.in_(list_owner_ids))
    if except_list_owner_ids:
        statement = statement.where(ShoppingList.owner_id.not_in(except_list_owner_ids))
    result = await session.execute(statement.order_by(ListMeal.list_id, ListMeal.position))
    return result.scalars().all()


async def recent_meal_ids(
    session: AsyncSession, user_id: str, owner_ids: Collection[str], limit: int
) -> list[str]:
    """The meals the user added to lists, most recently added (or added again) first, as far
    as they belong to the given owners."""
    last_added = func.max(ListMeal.last_added_at)
    result = await session.execute(
        select(ListMeal.meal_id)
        .join(Meal, Meal.id == ListMeal.meal_id)
        .where(ListMeal.added_by == user_id, Meal.owner_id.in_(owner_ids))
        .group_by(ListMeal.meal_id)
        .order_by(last_added.desc(), ListMeal.meal_id)
        .limit(limit)
    )
    return [meal_id for meal_id in result.scalars() if meal_id is not None]


# --- extra items ------------------------------------------------------------------------------


async def extras_for(
    session: AsyncSession, list_ids: Iterable[str]
) -> dict[str, list[ListExtraItem]]:
    """The extra items per list id that are not deleted, in the order they were added."""
    ids = set(list_ids)
    extras: dict[str, list[ListExtraItem]] = defaultdict(list)
    if ids:
        result = await session.execute(
            select(ListExtraItem)
            .where(ListExtraItem.list_id.in_(ids), ListExtraItem.deleted_at.is_(None))
            .order_by(ListExtraItem.list_id, ListExtraItem.created_at, ListExtraItem.id)
        )
        for row in result.scalars():
            extras[row.list_id].append(row)
    return extras


async def get_extra(session: AsyncSession, extra_id: str) -> ListExtraItem | None:
    """An extra item by id, on any list, deleted or not."""
    return await session.get(ListExtraItem, extra_id)


# --- line states ------------------------------------------------------------------------------


async def states_for(
    session: AsyncSession, list_ids: Iterable[str]
) -> dict[str, dict[str, ListLineState]]:
    """The line states per list id and line key."""
    ids = set(list_ids)
    states: dict[str, dict[str, ListLineState]] = defaultdict(dict)
    if ids:
        result = await session.execute(select(ListLineState).where(ListLineState.list_id.in_(ids)))
        for row in result.scalars():
            states[row.list_id][row.line_key] = row
    return states


async def get_state(session: AsyncSession, list_id: str, line_key: str) -> ListLineState | None:
    return await session.get(ListLineState, (list_id, line_key))


# --- ops ------------------------------------------------------------------------------------


async def processed_op_ids(session: AsyncSession, user_id: str, op_ids: Iterable[str]) -> set[str]:
    """Those of the user's op ids that were applied before (on any list; SYNC-05)."""
    ids = set(op_ids)
    result = await session.execute(
        select(ProcessedOp.op_id).where(ProcessedOp.user_id == user_id, ProcessedOp.op_id.in_(ids))
    )
    return set(result.scalars())


# --- lifecycle --------------------------------------------------------------------------------


async def delete_processed_ops_before(session: AsyncSession, cutoff: datetime) -> int:
    """Forget ops applied before `cutoff` (plan § 5.8); returns how many."""
    deleted = await session.scalars(
        delete(ProcessedOp).where(ProcessedOp.applied_at < cutoff).returning(ProcessedOp.op_id)
    )
    return len(deleted.all())


async def unshare_all_of(session: AsyncSession, owner_ids: Collection[str], now: datetime) -> None:
    """Turn the share switch off on every list of the owners (CPL-05)."""
    result = await session.execute(
        select(ShoppingList.id).where(
            ShoppingList.owner_id.in_(owner_ids), ShoppingList.shared_with_partner.is_(True)
        )
    )
    list_ids = list(result.scalars())
    if list_ids:
        await session.execute(
            update(ShoppingList)
            .where(ShoppingList.id.in_(list_ids))
            .values(shared_with_partner=False)
            .execution_options(synchronize_session="fetch")
        )
        await bump(session, list_ids, now)


async def transfer_shared(
    session: AsyncSession, from_owner_id: str, to_owner_id: str, now: datetime
) -> None:
    """Move the lists `from_owner_id` shares with their partner to `to_owner_id`, unshared
    (ADM-03)."""
    result = await session.execute(
        select(ShoppingList.id).where(
            ShoppingList.owner_id == from_owner_id, ShoppingList.shared_with_partner.is_(True)
        )
    )
    list_ids = list(result.scalars())
    if list_ids:
        await session.execute(
            update(ShoppingList)
            .where(ShoppingList.id.in_(list_ids))
            .values(owner_id=to_owner_id, shared_with_partner=False)
            .execution_options(synchronize_session="fetch")
        )
        await bump(session, list_ids, now)


# --- ingredients ------------------------------------------------------------------------------


def _lists_with_ingredient(ingredient_id: str) -> Subquery:
    frozen = (
        select(ListMeal.list_id)
        .join(ListMealIngredient, ListMealIngredient.list_meal_id == ListMeal.id)
        .where(ListMealIngredient.ingredient_id == ingredient_id)
    )
    extras = select(ListExtraItem.list_id).where(
        ListExtraItem.ingredient_id == ingredient_id, ListExtraItem.deleted_at.is_(None)
    )
    return union(frozen, extras).subquery()


async def count_with_ingredient(session: AsyncSession, ingredient_id: str) -> int:
    """How many lists have frozen rows or (not deleted) linked extra items of the
    ingredient."""
    lists = _lists_with_ingredient(ingredient_id)
    result = await session.execute(select(func.count()).select_from(lists))
    return result.scalar_one()


async def delete_deleted_extras_of(session: AsyncSession, ingredient_id: str) -> None:
    """Drop the tombstones of deleted extra items linked to the ingredient, so it can be
    deleted (they no longer count as references)."""
    await session.execute(
        delete(ListExtraItem).where(
            ListExtraItem.ingredient_id == ingredient_id, ListExtraItem.deleted_at.is_not(None)
        )
    )


async def lists_with_parts_of(session: AsyncSession, ingredient_id: str) -> set[str]:
    """The lists the ingredient has a line on: frozen rows, live meals with rows of it, and
    linked extra items that are not deleted."""
    statement = union(
        select(ListMeal.list_id)
        .join(ListMealIngredient, ListMealIngredient.list_meal_id == ListMeal.id)
        .where(ListMealIngredient.ingredient_id == ingredient_id),
        select(ListMeal.list_id)
        .join(MealIngredient, MealIngredient.meal_id == ListMeal.meal_id)
        .where(MealIngredient.ingredient_id == ingredient_id, ListMeal.frozen_at.is_(None)),
        select(ListExtraItem.list_id).where(
            ListExtraItem.ingredient_id == ingredient_id, ListExtraItem.deleted_at.is_(None)
        ),
    )
    result = await session.execute(statement)
    return set(result.scalars())


async def repoint_ingredient(session: AsyncSession, from_id: str, into_id: str) -> None:
    """Frozen rows and extra items of one ingredient now refer to another (merge, ING-05);
    the snapshots stay as they were."""
    await session.execute(
        update(ListMealIngredient)
        .where(ListMealIngredient.ingredient_id == from_id)
        .values(ingredient_id=into_id)
    )
    await session.execute(
        update(ListExtraItem)
        .where(ListExtraItem.ingredient_id == from_id)
        .values(ingredient_id=into_id)
    )


async def states_with_key(
    session: AsyncSession, line_key: str, *, list_ids: Collection[str] | None = None
) -> Sequence[ListLineState]:
    """The states of a line key, on the given lists (all lists if None)."""
    statement = select(ListLineState).where(ListLineState.line_key == line_key)
    if list_ids is not None:
        statement = statement.where(ListLineState.list_id.in_(list_ids))
    result = await session.execute(statement)
    return result.scalars().all()
