"""Lifecycle hooks between aggregates (plan § 6, deletion and lifecycle rules).

The account, ingredient and meal rules call these hooks at the right point of their write
transaction: meals (M4) fill in the ingredient references, shopping lists (M5a) detach meals
that go away or become invisible (LIST-15), move shared lists on user deletion (ADM-03) and
follow ingredient merges. Each hook runs inside the caller's transaction and must not commit;
`now` is the time of the triggering request.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lists import ingredient_key
from app.domain.units import BaseUnit, stops_fitting
from app.models import ListLineState
from app.repositories import lists as lists_repo
from app.repositories import meals as meals_repo
from app.repositories import users as users_repo
from app.services import access, detach


async def on_couple_ended(
    session: AsyncSession, user_a_id: str, user_b_id: str, *, now: datetime
) -> None:
    """Runs when a couple ends, before its rows are deleted (CPL-05): the share switch goes
    off on all lists of both users, so a later couple shares nothing automatically, and each
    one's meals are detached from the other's not-yet-frozen lists if they are no longer
    visible there (*meals public* off; LIST-15)."""
    await lists_repo.unshare_all_of(session, (user_a_id, user_b_id), now)
    users = await users_repo.by_ids(session, (user_a_id, user_b_id))
    for meal_owner, list_owner in ((user_a_id, user_b_id), (user_b_id, user_a_id)):
        if not users[meal_owner].meals_public:
            list_meals = await lists_repo.live_meals_of_owner(
                session, meal_owner, list_owner_ids=(list_owner,)
            )
            await detach.detach(session, list_meals, "unavailable", now=now)


async def on_meals_made_private(session: AsyncSession, user_id: str, *, now: datetime) -> None:
    """Runs when a user switches *meals public* off (VIS-02): their meals are detached from
    the not-yet-frozen lists of everyone but themselves and their partner (LIST-15)."""
    keep = {user_id}
    if (partner := await access.partner_id(session, user_id)) is not None:
        keep.add(partner)
    list_meals = await lists_repo.live_meals_of_owner(session, user_id, except_list_owner_ids=keep)
    await detach.detach(session, list_meals, "unavailable", now=now)


async def on_lists_made_private(session: AsyncSession, user_id: str, *, now: datetime) -> None:
    """Runs when a user switches *lists public* off (VIS-02).

    Visibility is computed on every read (and the list ETags change with it), so nothing needs
    to change.
    """


async def before_user_deleted(session: AsyncSession, user_id: str, *, now: datetime) -> None:
    """Runs first when an admin deletes a user (ADM-03), before the couple ends:

    1. the lists they share with their partner move to the partner, unshared;
    2. their meals are detached from every not-yet-frozen list they do not own, including the
       lists that just moved (LIST-15, reason `deleted`).

    Their own meals, remaining lists and sessions then go by `ON DELETE CASCADE`; their photo
    files are removed by `mealmate jobs cleanup`.
    """
    if (partner := await access.partner_id(session, user_id)) is not None:
        await lists_repo.transfer_shared(session, user_id, partner, now)
    list_meals = await lists_repo.live_meals_of_owner(
        session, user_id, except_list_owner_ids=(user_id,)
    )
    await detach.detach(session, list_meals, "deleted", now=now)


async def on_meal_deleted(session: AsyncSession, meal_id: str, *, now: datetime) -> None:
    """Runs when the owner deletes a meal (MEAL-07), before its row is deleted: it is detached
    from every not-yet-frozen list (LIST-15). Its rows and tags go by `ON DELETE CASCADE`;
    copies keep existing without their "based on"."""
    await detach.detach(
        session, await lists_repo.live_meals_of_meal(session, meal_id), "deleted", now=now
    )


async def ingredient_references(session: AsyncSession, ingredient_id: str) -> dict[str, int]:
    """References to an ingredient, counted per kind: its usage on the detail page; any of them
    blocks deleting it (ING-05) and is reported in the `ingredient.in_use` params.

    - `meals`: the meals with rows (`meal_ingredients`) of this ingredient;
    - `lists`: the lists with frozen rows (`list_meal_ingredients`) or linked extra items that
      are not deleted (`list_extra_items`) of this ingredient.
    """
    return {
        "meals": await meals_repo.count_with_ingredient(session, ingredient_id),
        "lists": await lists_repo.count_with_ingredient(session, ingredient_id),
    }


async def amounts_that_stop_fitting(
    session: AsyncSession, ingredient_id: str, before: BaseUnit, after: BaseUnit
) -> dict[str, int]:
    """The ingredient's amounts that fit `before` and won't fit `after` (`stops_fitting`, D-33),
    counted for a base-unit change (ING-02) or a merge (ING-05):

    - `meals`: the meals with such rows;
    - `lists`: the drafts with such linked extra items (lists being shopped and done lists keep
      the base unit they copied, LIST-11);
    - `amounts`: those rows and extra items.
    """
    meals = [
        meal_id
        for meal_id, amount, unit in await meals_repo.amounts_of(session, ingredient_id)
        if stops_fitting(amount, unit, before, after)
    ]
    lists = [
        list_id
        for list_id, amount, unit in await lists_repo.draft_amounts_of(session, ingredient_id)
        if stops_fitting(amount, unit, before, after)
    ]
    return {"meals": len(set(meals)), "lists": len(set(lists)), "amounts": len(meals) + len(lists)}


async def before_ingredient_deleted(session: AsyncSession, ingredient_id: str) -> None:
    """Runs when an admin deletes an ingredient nothing refers to (ING-05), before its row is
    deleted: the tombstones of deleted extra items linked to it go with it."""
    await lists_repo.delete_deleted_extras_of(session, ingredient_id)


async def on_ingredients_merged(
    session: AsyncSession, from_id: str, into_id: str, *, now: datetime
) -> None:
    """Runs when an admin merges ingredient `from_id` into `into_id` (ING-05), after its
    barcode moved (if the target has none) and before `from_id` is deleted.

    Meal rows (`meal_ingredients`), frozen list rows and extra items are repointed, keeping
    their positions and snapshots; a meal may then have two rows of the same ingredient, which
    is allowed. Line states move from `i:<from_id>` to `i:<into_id>`, per list by the lines
    the list has before the merge (a line without a stored state is neither hidden nor
    checked):

    - both ingredients have a line: the states merge, hidden only if both were, checked only
      if both were (otherwise the check-off details go too), the rest from `into_id`;
    - only one has a line: its state wins, a state of the other (kept for a line that may come
      back, LIST-07) goes;
    - neither has a line: the state of `into_id` stays, else the one of `from_id` moves.

    Every list whose lines change gets a new version.
    """
    from_lists = await lists_repo.lists_with_parts_of(session, from_id)
    into_lists = await lists_repo.lists_with_parts_of(session, into_id)
    await meals_repo.repoint_ingredient(session, from_id, into_id)
    await lists_repo.repoint_ingredient(session, from_id, into_id)
    old_key, new_key = ingredient_key(from_id), ingredient_key(into_id)
    sources = {state.list_id: state for state in await lists_repo.states_with_key(session, old_key)}
    changed = from_lists | set(sources)
    targets = {
        state.list_id: state
        for state in await lists_repo.states_with_key(session, new_key, list_ids=changed)
    }
    for list_id in sorted(changed):
        source, target = sources.get(list_id), targets.get(list_id)
        if list_id in from_lists and list_id in into_lists:
            if target is not None:
                target.hidden = target.hidden and source is not None and source.hidden
                target.checked = target.checked and source is not None and source.checked
                if not target.checked:
                    _uncheck(target)
        elif list_id in from_lists and target is not None:
            if source is None:
                await session.delete(target)
            else:
                _copy_state(source, target)
        elif target is None and list_id not in into_lists and source is not None:
            source.line_key = new_key
            continue
        if source is not None:
            await session.delete(source)
    await session.flush()
    await lists_repo.bump(session, changed, now)


def _uncheck(state: ListLineState) -> None:
    state.checked = False
    state.checked_at = state.checked_by = state.checked_op_id = state.checked_snapshot = None


def _copy_state(source: ListLineState, target: ListLineState) -> None:
    target.hidden, target.checked = source.hidden, source.checked
    target.checked_at, target.checked_by = source.checked_at, source.checked_by
    target.checked_op_id, target.checked_snapshot = source.checked_op_id, source.checked_snapshot
