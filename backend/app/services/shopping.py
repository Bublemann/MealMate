"""Shopping mode: starting it, checking lines off, finishing and reopening (LIST-10..12,
SHOP-04/06, SYNC-06, plan §§ 5.7 and 5.8).

These rules run inside the caller's write transaction, after its access checks: the list
service (start shopping, reopen, editing while shopping), the ops service (check-off, finish)
and the demo data use them. The caller records the change (version, `updated_at`).
"""

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode
from app.models import ListExtraItem, ListLineState, ShoppingList
from app.repositories import ingredients as ingredients_repo
from app.repositories import lists as lists_repo
from app.services import aggregation, detach

# A time from the client counts as at most this far in the future (plan § 5.8), so a phone
# with a wrong clock cannot win every later conflict.
MAX_CLOCK_AHEAD = timedelta(minutes=5)
# A check-off may be this far before shopping started, so a phone whose clock is a little
# behind the server's can check off right after starting.
MAX_CLOCK_BEHIND = timedelta(minutes=5)


async def snapshot_extras(session: AsyncSession, extras: Iterable[ListExtraItem]) -> None:
    """Give the linked extra items without one the snapshot of their ingredient's attributes
    (LIST-11); from then on ingredient edits no longer change their amounts."""
    pending = [
        extra
        for extra in extras
        if extra.ingredient_id is not None and extra.attrs_snapshot is None
    ]
    ingredients = await ingredients_repo.by_ids(
        session, (str(extra.ingredient_id) for extra in pending)
    )
    for extra in pending:
        extra.attrs_snapshot = aggregation.attrs_snapshot(ingredients[str(extra.ingredient_id)])


async def start(session: AsyncSession, shopping_list: ShoppingList, *, now: datetime) -> None:
    """Start shopping a draft (LIST-11, plan § 5.7): freeze its live meals (they keep their
    meal), snapshot its linked extra items, store a state for every line it has now (so only
    lines that appear later are `new`, LIST-12; hidden lines keep theirs) and set the status."""
    list_id = shopping_list.id
    await detach.freeze(session, (await lists_repo.meals_for(session, [list_id]))[list_id], now=now)
    await snapshot_extras(session, (await lists_repo.extras_for(session, [list_id]))[list_id])
    await session.flush()
    content = await aggregation.load(session, [shopping_list])
    states = content.states.get(list_id, {})
    session.add_all(
        ListLineState(list_id=list_id, line_key=line_key, checked=False, hidden=False)
        for line_key in aggregation.current_lines(content, shopping_list)
        if line_key not in states
    )
    shopping_list.status = "shopping"
    shopping_list.shopping_started_at = now


def op_time(at: datetime, *, now: datetime) -> datetime | None:
    """The time a check-off or finishing op counts with: the client's, in UTC, at most
    `MAX_CLOCK_AHEAD` after the server's; None if it has no UTC time (a time zone moves it
    past the ends of the calendar)."""
    try:
        utc = at.astimezone(UTC)
    except OverflowError, ValueError:
        return None
    return min(utc, now + MAX_CLOCK_AHEAD)


def check_refused(shopping_list: ShoppingList, at: datetime) -> ErrorCode | None:
    """Why a line of the list may not be checked or unchecked at `at`, if so (SYNC-06): not in
    a draft, nor for taps before shopping started (more than `MAX_CLOCK_BEHIND`); on a done
    list only for taps before it was finished."""
    started_at = shopping_list.shopping_started_at
    if shopping_list.status == "draft" or (
        started_at is not None and at < started_at - MAX_CLOCK_BEHIND
    ):
        return ErrorCode.LIST_NOT_SHOPPING
    finished_at = shopping_list.finished_at
    if shopping_list.status == "done" and (finished_at is None or at > finished_at):
        return ErrorCode.LIST_DONE
    return None


def _wins(state: ListLineState, at: datetime, op_id: str) -> bool:
    """Last write wins (SYNC-06): the later tap, and of two at the same time the higher op
    id."""
    if state.checked_at is None:
        return True
    return (at, op_id) > (state.checked_at, state.checked_op_id or "")


async def set_checked(
    session: AsyncSession,
    shopping_list: ShoppingList,
    line_key: str,
    *,
    checked: bool,
    snapshot: dict[str, Any],
    user_id: str,
    at: datetime,
    op_id: str,
) -> bool:
    """Check a line off (with the `snapshot` of what it looked like, plan § 5.7) or uncheck
    it, unless the stored state comes from a later tap; whether it did. An uncheck keeps its
    time and op id too, so last-write-wins works both ways."""
    state = await lists_repo.get_state(session, shopping_list.id, line_key)
    if state is None:
        state = ListLineState(
            list_id=shopping_list.id, line_key=line_key, checked=False, hidden=False
        )
        session.add(state)
    elif not _wins(state, at, op_id):
        return False
    state.checked = checked
    state.checked_at, state.checked_op_id = at, op_id
    state.checked_by = user_id if checked else None
    state.checked_snapshot = snapshot if checked else None
    await session.flush()
    return True


def finish(shopping_list: ShoppingList, *, at: datetime, now: datetime) -> None:
    """The list is done (SHOP-04): read-only, in the history. It counts as finished at the
    tap (`at`, so a finish sent later lands in the right week), but not before shopping
    started nor after `now`."""
    started_at = shopping_list.shopping_started_at
    shopping_list.status = "done"
    shopping_list.finished_at = min(at if started_at is None else max(at, started_at), now)


def reopen(shopping_list: ShoppingList) -> None:
    """Back to shopping (SHOP-06); it leaves the history until it is finished again."""
    shopping_list.status = "shopping"
    shopping_list.finished_at = None
