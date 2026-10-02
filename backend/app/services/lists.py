"""Shopping lists: the list feed, create, rename, share, delete, meals with servings, extra
items, hidden lines, copies, starting to shop, reopening and shopping again (LIST-01..15,
SHOP-05/06, CPL-02/03, VIS-03/06, UI-02).

Who may see or change a list is decided by `services.access`; which meals on it the viewer
may see (VIS-06) by the meal rules. The lines come from `services.aggregation`, the rules of
shopping mode from `services.shopping`. Every change bumps the list's `version` and
`updated_at` in the same transaction (plan § 5.7).

The states (LIST-10): meals, servings and extra items change in a draft and while shopping
(LIST-12: a meal added while shopping is frozen at once, a linked extra item snapshotted); a
done list is read-only (409 `list.done`) until it is reopened. Lines are hidden and restored
only in a draft (409 `list.not_draft`).
"""

import secrets
from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from datetime import datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ApiError,
    ErrorCode,
    FieldErrorCode,
    FieldProblem,
    not_found,
    validation_error,
)
from app.db.ids import new_id
from app.domain.lists import (
    FEED_PAGE_SIZE,
    LIST_STATUSES,
    REMINDER_SEED_MAX,
    DetachedReason,
    FeedPosition,
    ListStatus,
    feed_cursor,
    feed_position,
    raised_servings,
)
from app.domain.reference import OTHER_CATEGORY
from app.domain.units import Unit
from app.media import urls as media_urls
from app.media.store import MediaStore
from app.models import ListExtraItem, ListLineState, ListMeal, ShoppingList
from app.models import Meal as MealRow
from app.repositories import ingredients as ingredients_repo
from app.repositories import lists as lists_repo
from app.repositories import meals as meals_repo
from app.repositories import reference as reference_repo
from app.schemas.lists import (
    ExtraItem,
    ExtraItemCreate,
    ExtraItemUpdate,
    ListCopyResult,
    ListCreate,
    ListDetail,
    ListFeedPage,
    ListMealAdd,
    ListMealEntry,
    ListMealUpdate,
    ListSummary,
    ListUpdate,
)
from app.schemas.users import UserRef
from app.services import access, aggregation, detach, shopping
from app.services.access import ListRights
from app.services.list_cache import CachedList, ListCache
from app.services.principal import Principal
from app.services.users import hidden_by, user_refs

# The local copy holds the drafts and lists being shopped one can edit (SYNC-02).
COPY_STATUSES: tuple[ListStatus, ...] = ("draft", "shopping")


def _status(shopping_list: ShoppingList) -> ListStatus:
    return cast(ListStatus, shopping_list.status)


def _require_draft(shopping_list: ShoppingList) -> None:
    if shopping_list.status != "draft":
        raise ApiError(ErrorCode.LIST_NOT_DRAFT, status_code=409)


def _require_not_done(shopping_list: ShoppingList) -> None:
    """Done lists are read-only (LIST-10)."""
    if shopping_list.status == "done":
        raise ApiError(ErrorCode.LIST_DONE, status_code=409)


def _require_done(shopping_list: ShoppingList) -> None:
    if shopping_list.status != "done":
        raise ApiError(ErrorCode.LIST_NOT_DONE, status_code=409)


def _field(name: str, code: FieldErrorCode) -> FieldProblem:
    return FieldProblem(("body", name), code)


async def touch(session: AsyncSession, shopping_list: ShoppingList, now: datetime) -> None:
    """Record a change of the list (new version, `updated_at`) and reload both."""
    await session.flush()
    await lists_repo.bump(session, [shopping_list.id], now)
    await session.refresh(shopping_list, ["version", "updated_at"])


def _meal_entry(
    content: aggregation.ListContent,
    media: MediaStore,
    list_meal: ListMeal,
    refs: Mapping[str, UserRef],
    *,
    private: bool,
    now: datetime,
) -> ListMealEntry:
    meal = content.live_meal(list_meal)
    meal_servings = list_meal.meal_servings_snapshot if meal is None else meal.servings
    linked = content.linked_meal(list_meal)
    detached = cast(DetachedReason | None, list_meal.detached_reason)
    if private:
        return ListMealEntry(
            id=list_meal.id,
            meal_id=None,
            name=None,
            private=True,
            owner=None,
            thumb_url=None,
            servings=list_meal.servings,
            meal_servings=meal_servings,
            detached=detached,
        )
    owner_id = list_meal.meal_owner_id_snapshot
    return ListMealEntry(
        id=list_meal.id,
        meal_id=list_meal.meal_id,
        name=aggregation.meal_name(content, list_meal),
        private=False,
        owner=None if owner_id is None else refs.get(owner_id),
        thumb_url=(
            None
            if linked is None or linked.photo_key is None
            else media.thumb_url(linked.photo_key, now=now)
        ),
        servings=list_meal.servings,
        meal_servings=meal_servings,
        detached=detached,
    )


def _extra_item(row: ListExtraItem, refs: Mapping[str, UserRef]) -> ExtraItem:
    return ExtraItem(
        id=row.id,
        ingredient_id=row.ingredient_id,
        text=row.text,
        amount=row.amount,
        unit=None if row.unit is None else Unit(row.unit),
        amount_text=row.amount_text,
        category_id=row.category_id,
        added_by=None if row.added_by is None else refs.get(row.added_by),
        created_at=row.created_at,
    )


def private_meals(list_meals: Collection[ListMeal], visible_owner_ids: Collection[str]) -> set[str]:
    """The list meals whose details the viewer may not see (VIS-06): meals of owners whose
    meals they may not see. A meal's owner never changes, so the owner snapshot decides for
    live and detached meals alike; a detached meal of a deleted user stays private."""
    return {row.id for row in list_meals if row.meal_owner_id_snapshot not in visible_owner_ids}


async def list_detail(
    session: AsyncSession,
    media: MediaStore,
    viewer_id: str,
    shopping_list: ShoppingList,
    rights: ListRights,
    *,
    now: datetime,
) -> ListDetail:
    """The list as the viewer sees it."""
    content = await aggregation.load(session, [shopping_list])
    visible = await access.owners_visible_to(session, viewer_id, rights.viewer_partner_id, "meals")
    list_meals = content.meals.get(shopping_list.id, [])
    extras = content.extras.get(shopping_list.id, [])
    refs = await user_refs(
        session,
        [
            shopping_list.owner_id,
            *(row.meal_owner_id_snapshot for row in list_meals),
            *(row.added_by for row in extras),
            *(row.checked_by for row in content.states.get(shopping_list.id, {}).values()),
        ],
    )
    private = private_meals(list_meals, visible)
    return ListDetail(
        id=shopping_list.id,
        name=shopping_list.name,
        status=_status(shopping_list),
        version=shopping_list.version,
        created_at=shopping_list.created_at,
        updated_at=shopping_list.updated_at,
        shopping_started_at=shopping_list.shopping_started_at,
        finished_at=shopping_list.finished_at,
        owner=refs[shopping_list.owner_id],
        is_owner=rights.is_owner,
        can_edit=rights.can_edit,
        shared_with_partner=shopping_list.shared_with_partner,
        reminder_seed=shopping_list.reminder_seed,
        meals=[
            _meal_entry(content, media, row, refs, private=row.id in private, now=now)
            for row in list_meals
        ],
        lines=aggregation.lines(content, shopping_list, private_meals=private, refs=refs),
        extra_items=[_extra_item(row, refs) for row in extras],
    )


# --- lists --------------------------------------------------------------------------------


async def _summaries(
    session: AsyncSession,
    principal: Principal,
    partner: str | None,
    rows: Sequence[ShoppingList],
) -> list[ListSummary]:
    content = await aggregation.load(session, rows)
    refs = await user_refs(session, (row.owner_id for row in rows))
    return [
        ListSummary(
            id=row.id,
            name=row.name,
            status=_status(row),
            created_at=row.created_at,
            updated_at=row.updated_at,
            finished_at=row.finished_at,
            owner=refs[row.owner_id],
            is_owner=row.owner_id == principal.user_id,
            can_edit=row.owner_id == principal.user_id
            or (row.owner_id == partner and row.shared_with_partner),
            shared_with_partner=row.shared_with_partner,
            meal_count=len(content.meals.get(row.id, [])),
            line_count=aggregation.line_count(content, row),
        )
        for row in rows
    ]


async def list_feed(
    session: AsyncSession, principal: Principal, *, cursor: str | None
) -> ListFeedPage:
    """A page of the list feed (UI-02, D-24, D-26): every list the principal can see: their own,
    all of their partner's (CPL-02/04) and those of owners whose *lists public* switch is on
    (VIS-02/03), as far as their saved filters show them. The user filter hides every list of
    an unticked owner, the principal's own and shared ones too; the state filter hides the
    lists in unticked states. Newest created first, ties by id, `FEED_PAGE_SIZE` per page;
    `cursor` is the previous page's `next_cursor` (422 if it is not one)."""
    after: FeedPosition | None = None
    if cursor is not None:
        after = feed_position(cursor)
        if after is None:
            raise validation_error([FieldProblem(("query", "cursor"), FieldErrorCode.INVALID)])
    async with session.begin():
        partner = await access.partner_id(session, principal.user_id)
        visible = await access.owners_visible_to(session, principal.user_id, partner, "lists")
        owners = visible - await hidden_by(session, principal.user_id, "lists")
        hidden_states = await hidden_by(session, principal.user_id, "list_states")
        statuses = [status for status in LIST_STATUSES if status not in hidden_states]
        rows = await lists_repo.feed(session, owners, statuses, after, FEED_PAGE_SIZE + 1)
        page = rows[:FEED_PAGE_SIZE]
        next_cursor = (
            feed_cursor(FeedPosition(page[-1].created_at, page[-1].id))
            if len(rows) > FEED_PAGE_SIZE
            else None
        )
        return ListFeedPage(
            lists=await _summaries(session, principal, partner, page), next_cursor=next_cursor
        )


def _detail_json(
    session: AsyncSession,
    media: MediaStore,
    viewer_id: str,
    shopping_list: ShoppingList,
    rights: ListRights,
    *,
    now: datetime,
) -> Callable[[], Awaitable[bytes]]:
    """A build of the list's response body for the list cache."""

    async def build() -> bytes:
        detail = await list_detail(session, media, viewer_id, shopping_list, rights, now=now)
        return detail.model_dump_json().encode()

    return build


async def sync_lists(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    cache: ListCache,
    generation: int,
    *,
    now: datetime,
) -> list[CachedList]:
    """The local copy for offline use (SYNC-02): the response bodies of `GET /api/lists/{id}`
    of every list the principal can edit that is a draft or being shopped (their own and those
    their partner shares with them, CPL-02), most recently edited first. Each body comes from
    the list cache (`generation` read before this starts), so the copy costs one detail build
    per list that changed since the last poll or sync of it."""
    async with session.begin():
        partner = await access.partner_id(session, principal.user_id)
        rows = await lists_repo.mine(session, principal.user_id, partner, COPY_STATUSES)
        entries: list[CachedList] = []
        for row in rows:
            rights = ListRights(
                is_owner=row.owner_id == principal.user_id,
                can_edit=True,
                viewer_partner_id=partner,
            )
            build = _detail_json(session, media, principal.user_id, row, rights, now=now)
            key = (row.id, principal.user_id, media_urls.expiry(now))
            entries.append(await cache.get_or_build(key, generation, build))
        return entries


async def _new_list(
    session: AsyncSession, principal: Principal, name: str | None, *, now: datetime
) -> tuple[ShoppingList, ListRights]:
    """A new draft of the principal, shared with their partner if they have one (CPL-02), and
    the principal's rights on it."""
    partner = await access.partner_id(session, principal.user_id)
    shopping_list = ShoppingList(
        owner_id=principal.user_id,
        name=name,
        status="draft",
        shared_with_partner=partner is not None,
        version=0,
        reminder_seed=secrets.randbelow(REMINDER_SEED_MAX + 1),
        created_at=now,
        updated_at=now,
    )
    session.add(shopping_list)
    await session.flush()
    return shopping_list, ListRights(is_owner=True, can_edit=True, viewer_partner_id=partner)


async def create_list(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    body: ListCreate,
    *,
    now: datetime,
) -> ListDetail:
    """A new, empty draft (LIST-01)."""
    async with session.begin():
        shopping_list, rights = await _new_list(session, principal, body.name, now=now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


async def get_list(
    session: AsyncSession, media: MediaStore, principal: Principal, list_id: str, *, now: datetime
) -> ListDetail:
    """A list the principal may see (404 otherwise)."""
    async with session.begin():
        shopping_list, rights = await access.require_list_view(session, principal, list_id)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


async def update_list(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    body: ListUpdate,
    *,
    now: datetime,
) -> ListDetail:
    """Rename (editors, LIST-02) or switch sharing (the owner, CPL-02; only on while in a
    couple); not once the list is done (LIST-10)."""
    sent = body.model_fields_set
    async with session.begin():
        shopping_list, rights = await access.require_list_edit(session, principal, list_id)
        _require_not_done(shopping_list)
        if "shared_with_partner" in sent and not rights.is_owner:
            raise ApiError(ErrorCode.FORBIDDEN, status_code=403)
        changed = False
        if "name" in sent and body.name != shopping_list.name:
            shopping_list.name = body.name
            changed = True
        share = body.shared_with_partner
        if share is not None and share != shopping_list.shared_with_partner:
            if share and await access.partner_id(session, shopping_list.owner_id) is None:
                raise validation_error([_field("shared_with_partner", FieldErrorCode.INVALID)])
            shopping_list.shared_with_partner = share
            changed = True
        if changed:
            await touch(session, shopping_list, now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


async def delete_list(session: AsyncSession, principal: Principal, list_id: str) -> None:
    """Delete a list in any state (the owner, LIST-13); its content goes with it."""
    async with session.begin():
        shopping_list, _ = await access.require_list_owner(session, principal, list_id)
        await session.delete(shopping_list)


async def _copy(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    source: ShoppingList,
    *,
    now: datetime,
) -> ListCopyResult:
    """A new draft of the principal from a list: same name, the meals that still exist and
    they may see (the current versions, live again), with their servings, and the extra items
    (unchecked, without snapshots). `left_out` counts the other meals (VIS-06). Hidden lines
    and check states are not copied (LIST-07)."""
    visible = await access.visible_owner_ids(session, principal.user_id, "meals")
    list_meals = (await lists_repo.meals_for(session, [source.id]))[source.id]
    meals = await meals_repo.by_ids(session, (row.meal_id for row in list_meals))
    kept = [
        (row, meals[row.meal_id])
        for row in list_meals
        if row.meal_id in meals and meals[row.meal_id].owner_id in visible
    ]
    extras = (await lists_repo.extras_for(session, [source.id]))[source.id]
    copy, rights = await _new_list(session, principal, source.name, now=now)
    for position, (row, meal) in enumerate(kept):
        session.add(_list_meal(copy, meal, row.servings, position, principal, now=now))
    for extra in extras:
        session.add(
            ListExtraItem(
                id=new_id(),
                list_id=copy.id,
                ingredient_id=extra.ingredient_id,
                text=extra.text,
                amount=extra.amount,
                unit=extra.unit,
                amount_text=extra.amount_text,
                category_id=extra.category_id,
                added_by=principal.user_id,
                created_at=now,
                updated_at=now,
            )
        )
    await session.flush()
    detail = await list_detail(session, media, principal.user_id, copy, rights, now=now)
    return ListCopyResult(list=detail, left_out=len(list_meals) - len(kept))


async def copy_list(
    session: AsyncSession, media: MediaStore, principal: Principal, list_id: str, *, now: datetime
) -> ListCopyResult:
    """Copy a list the principal may see, in any state, into a new draft of theirs
    (VIS-03)."""
    async with session.begin():
        source, _ = await access.require_list_view(session, principal, list_id)
        return await _copy(session, media, principal, source, now=now)


async def shop_again(
    session: AsyncSession, media: MediaStore, principal: Principal, list_id: str, *, now: datetime
) -> ListCopyResult:
    """ "Shop again" (SHOP-06): a done list the principal may see (409 `list.not_done` for
    others) into a new draft of theirs, as a copy."""
    async with session.begin():
        source, _ = await access.require_list_view(session, principal, list_id)
        _require_done(source)
        return await _copy(session, media, principal, source, now=now)


# --- shopping mode ------------------------------------------------------------------------


async def start_shopping(
    session: AsyncSession, media: MediaStore, principal: Principal, list_id: str, *, now: datetime
) -> ListDetail:
    """ "Start shopping" (LIST-10/11) on a draft the principal may edit (409 `list.not_draft`
    otherwise): its meals are frozen and its linked extra items snapshotted, its current lines
    get a state (later ones are `new`)."""
    async with session.begin():
        shopping_list, rights = await access.require_list_edit(session, principal, list_id)
        _require_draft(shopping_list)
        await shopping.start(session, shopping_list, now=now)
        await touch(session, shopping_list, now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


async def reopen_list(
    session: AsyncSession, media: MediaStore, principal: Principal, list_id: str, *, now: datetime
) -> ListDetail:
    """ "Reopen" (SHOP-06): a done list the principal may edit goes back to shopping (409
    `list.not_done` for other states), with its check states."""
    async with session.begin():
        shopping_list, rights = await access.require_list_edit(session, principal, list_id)
        _require_done(shopping_list)
        shopping.reopen(shopping_list)
        await touch(session, shopping_list, now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


# --- meals on a list ----------------------------------------------------------------------


def _list_meal(
    shopping_list: ShoppingList,
    meal: MealRow,
    servings: int,
    position: int,
    principal: Principal,
    *,
    now: datetime,
) -> ListMeal:
    return ListMeal(
        list_id=shopping_list.id,
        meal_id=meal.id,
        servings=servings,
        meal_servings_snapshot=meal.servings,
        meal_name_snapshot=meal.name,
        meal_owner_id_snapshot=meal.owner_id,
        added_by=principal.user_id,
        last_added_at=now,
        position=position,
        created_at=now,
        updated_at=now,
    )


async def _editable(
    session: AsyncSession, principal: Principal, list_id: str
) -> tuple[ShoppingList, ListRights]:
    """A list whose meals and extra items the principal may change: in a draft or while
    shopping (LIST-12), not once it is done."""
    shopping_list, rights = await access.require_list_edit(session, principal, list_id)
    _require_not_done(shopping_list)
    return shopping_list, rights


async def add_meal(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    body: ListMealAdd,
    *,
    now: datetime,
) -> ListDetail:
    """Add a meal the principal may see (LIST-03, else 422 `meal_id` `invalid`), with the
    meal's servings unless given; a meal already on the list gets that many more servings
    instead (LIST-04). Either way it counts as added by the principal now (MEAL-09). While
    shopping, a new meal is frozen at once (LIST-11)."""
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        meal = await meals_repo.get(session, body.meal_id)
        if meal is None or not await access.may_view_meals_of(
            session, principal.user_id, meal.owner_id
        ):
            raise validation_error([_field("meal_id", FieldErrorCode.INVALID)])
        servings = meal.servings if body.servings is None else body.servings
        existing = await lists_repo.meal_on_list(session, shopping_list.id, meal.id)
        if existing is not None:
            existing.servings = raised_servings(existing.servings, servings)
            existing.added_by, existing.last_added_at = principal.user_id, now
            existing.updated_at = now
        else:
            position = await lists_repo.next_meal_position(session, shopping_list.id)
            list_meal = _list_meal(shopping_list, meal, servings, position, principal, now=now)
            session.add(list_meal)
            if shopping_list.status != "draft":
                await session.flush()
                await detach.freeze(session, [list_meal], now=now)
        await touch(session, shopping_list, now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


async def _list_meal_of(session: AsyncSession, list_id: str, list_meal_id: str) -> ListMeal:
    list_meal = await lists_repo.get_meal(session, list_id, list_meal_id)
    if list_meal is None:
        raise not_found()
    return list_meal


async def update_meal(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    list_meal_id: str,
    body: ListMealUpdate,
    *,
    now: datetime,
) -> ListDetail:
    """Set the servings of a meal on the list (LIST-04), detached meals included."""
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        list_meal = await _list_meal_of(session, shopping_list.id, list_meal_id)
        if list_meal.servings != body.servings:
            list_meal.servings = body.servings
            list_meal.updated_at = now
            await touch(session, shopping_list, now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


async def remove_meal(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    list_meal_id: str,
    *,
    now: datetime,
) -> ListDetail:
    """Take a meal off the list, also one that is no longer available (LIST-15)."""
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        list_meal = await _list_meal_of(session, shopping_list.id, list_meal_id)
        await session.delete(list_meal)
        await touch(session, shopping_list, now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


# --- extra items --------------------------------------------------------------------------


def _create_problems(body: ExtraItemCreate) -> list[FieldProblem]:
    """Exactly one of ingredient and text, and only the fields of that kind (LIST-06)."""
    if body.ingredient_id is None and body.text is None:
        return [_field("text", FieldErrorCode.REQUIRED)]
    if body.ingredient_id is not None and body.text is not None:
        return [_field("text", FieldErrorCode.INVALID)]
    if body.ingredient_id is not None:
        problems = [
            _field(name, FieldErrorCode.INVALID)
            for name in ("amount_text", "category_id")
            if getattr(body, name) is not None
        ]
        if body.unit is not None and body.amount is None:
            problems.append(_field("amount", FieldErrorCode.REQUIRED))
        return problems
    return [
        _field(name, FieldErrorCode.INVALID)
        for name in ("amount", "unit")
        if getattr(body, name) is not None
    ]


async def _reference_problems(
    session: AsyncSession, *, ingredient_id: str | None, category_id: str | None
) -> list[FieldProblem]:
    problems = []
    if ingredient_id is not None and await ingredients_repo.get(session, ingredient_id) is None:
        problems.append(_field("ingredient_id", FieldErrorCode.INVALID))
    if category_id is not None and await reference_repo.get_category(session, category_id) is None:
        problems.append(_field("category_id", FieldErrorCode.INVALID))
    return problems


async def other_category_id(session: AsyncSession) -> str:
    other = await reference_repo.category_by_key(session, OTHER_CATEGORY)
    if other is None:  # pragma: no cover -- seeded by migration 0003, never deleted (REF-01)
        raise RuntimeError("the 'other' category is missing")
    return other.id


def _stored_unit(amount: float | None, unit: Unit | str | None) -> str | None:
    """An amount without a unit counts as pieces."""
    if amount is not None and unit is None:
        return Unit.PIECE.value
    return None if unit is None else Unit(unit).value


async def add_extra(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    body: ExtraItemCreate,
    *,
    now: datetime,
) -> tuple[ListDetail, bool]:
    """Add an extra item (LIST-06) and tell whether it is new: an `id` already on this list
    changes nothing (a repeated request); one on another list is refused (422 `id` `taken`).
    While shopping, a linked item gets its snapshot at once (LIST-11)."""
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        if body.id is not None and (existing := await lists_repo.get_extra(session, body.id)):
            if existing.list_id != shopping_list.id:
                raise validation_error([_field("id", FieldErrorCode.TAKEN)])
            detail = await list_detail(
                session, media, principal.user_id, shopping_list, rights, now=now
            )
            return detail, False
        problems = _create_problems(body)
        problems += await _reference_problems(
            session, ingredient_id=body.ingredient_id, category_id=body.category_id
        )
        if problems:
            raise validation_error(problems)
        linked = body.ingredient_id is not None
        extra = ListExtraItem(
            id=body.id or new_id(),
            list_id=shopping_list.id,
            ingredient_id=body.ingredient_id,
            text=body.text,
            amount=body.amount,
            unit=_stored_unit(body.amount, body.unit),
            amount_text=body.amount_text,
            category_id=(None if linked else body.category_id or await other_category_id(session)),
            added_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(extra)
        if shopping_list.status != "draft":
            await shopping.snapshot_extras(session, [extra])
        await touch(session, shopping_list, now)
        detail = await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now
        )
        return detail, True


async def _extra_of(session: AsyncSession, list_id: str, extra_id: str) -> ListExtraItem:
    """An extra item of the list that is not deleted (404 otherwise)."""
    extra = await lists_repo.get_extra(session, extra_id)
    if extra is None or extra.list_id != list_id or extra.deleted_at is not None:
        raise not_found()
    return extra


async def update_extra(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    extra_id: str,
    body: ExtraItemUpdate,
    *,
    now: datetime,
) -> ListDetail:
    """Change the fields that were sent; a linked item stays linked and a free-text item
    stays free text (the other kind's fields are refused). While shopping, a linked item
    moved to another ingredient takes that one's snapshot."""
    sent = body.model_fields_set
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        extra = await _extra_of(session, shopping_list.id, extra_id)
        linked = extra.ingredient_id is not None
        other_kind = (
            ("text", "amount_text", "category_id")
            if linked
            else ("ingredient_id", "amount", "unit")
        )
        problems = [_field(name, FieldErrorCode.INVALID) for name in other_kind if name in sent]
        values: dict[str, object]
        if linked:
            amount = body.amount if "amount" in sent else extra.amount
            unit: Unit | str | None = body.unit if "unit" in sent else extra.unit
            if amount is None and "unit" not in sent:
                unit = None  # clearing the amount clears its unit
            if unit is not None and amount is None:
                problems.append(_field("amount", FieldErrorCode.REQUIRED))
            values = {
                "ingredient_id": body.ingredient_id or extra.ingredient_id,
                "amount": amount,
                "unit": _stored_unit(amount, unit),
            }
        else:
            values = {
                "text": body.text or extra.text,
                "amount_text": body.amount_text if "amount_text" in sent else extra.amount_text,
                "category_id": body.category_id or extra.category_id,
            }
        problems += await _reference_problems(
            session,
            ingredient_id=body.ingredient_id if linked else None,
            category_id=None if linked else body.category_id,
        )
        if problems:
            raise validation_error(problems)
        if any(getattr(extra, name) != value for name, value in values.items()):
            if linked and values["ingredient_id"] != extra.ingredient_id:
                extra.attrs_snapshot = None
            for name, value in values.items():
                setattr(extra, name, value)
            if shopping_list.status != "draft":
                await shopping.snapshot_extras(session, [extra])
            extra.updated_at = now
            await touch(session, shopping_list, now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


async def delete_extra(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    extra_id: str,
    *,
    now: datetime,
) -> ListDetail:
    """Delete an extra item; a tombstone stays for offline clients (SYNC)."""
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        extra = await _extra_of(session, shopping_list.id, extra_id)
        extra.deleted_at = now
        extra.updated_at = now
        await touch(session, shopping_list, now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)


# --- lines --------------------------------------------------------------------------------


async def set_line_hidden(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    line_key: str,
    *,
    hidden: bool,
    now: datetime,
) -> ListDetail:
    """Remove a line for this list only, or restore it (LIST-07; in a draft). Any well-formed
    key is accepted, also one without a line right now: its state stays for when the line
    (re)appears. Nothing is remembered for other lists."""
    async with session.begin():
        shopping_list, rights = await access.require_list_edit(session, principal, list_id)
        _require_draft(shopping_list)
        state = await lists_repo.get_state(session, shopping_list.id, line_key)
        if state is None and hidden:
            session.add(
                ListLineState(
                    list_id=shopping_list.id, line_key=line_key, checked=False, hidden=True
                )
            )
            await touch(session, shopping_list, now)
        elif state is not None and state.hidden != hidden:
            state.hidden = hidden
            await touch(session, shopping_list, now)
        return await list_detail(session, media, principal.user_id, shopping_list, rights, now=now)
