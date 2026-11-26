"""Shopping lists: the list feed, create, rename, share, delete, meals with servings, extra
items, hidden lines, copies, starting to shop, reopening and shopping again, and the due
recurring items a draft offers (LIST-01..16, SHOP-05/06, CPL-02/03, VIS-03/06, UI-02).

Who may see or change a list is decided by `services.access`; which meals on it the viewer
may see (VIS-06) by the meal rules. The lines come from `services.aggregation`, the rules of
shopping mode from `services.shopping`. Every change bumps the list's `version` and
`updated_at` in the same transaction (plan § 5.7).

The states (LIST-10): meals, servings and extra items change in a draft and while shopping
(LIST-12: a meal added while shopping is frozen at once, a linked extra item snapshotted); a
done list is read-only (409 `list.done`) until it is reopened, except that its meals are marked
eaten (SHOP-07). Lines are hidden and restored only in a draft (409 `list.not_draft`).

Leftover meals (LIST-17, D-58): a new draft gets the uneaten meals of the last done list the
principal can edit, if it was finished at most `LEFTOVER_DAYS` ago, as leftovers of the meal
they come from (the source; a leftover of a leftover is one of its source). Marking a leftover
eaten, on any list, marks its source, and bumps every list that shows it.
"""

from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from datetime import datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

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
    LEFTOVER_DAYS,
    LIST_STATUSES,
    DetachedReason,
    FeedPosition,
    ListStatus,
    feed_cursor,
    feed_position,
    raised_servings,
)
from app.domain.owners import owner_key_of
from app.domain.recurring import local_date
from app.domain.reference import OTHER_CATEGORY
from app.domain.units import BaseUnit, Unit, counted_unit, fits
from app.media import urls as media_urls
from app.media.store import MediaStore
from app.models import (
    Item,
    ListExtraItem,
    ListHiddenDueItem,
    ListLineState,
    ListMeal,
    ShoppingList,
)
from app.models import Meal as MealRow
from app.repositories import items as items_repo
from app.repositories import lists as lists_repo
from app.repositories import meals as meals_repo
from app.repositories import reference as reference_repo
from app.schemas.items import base_unit_name
from app.schemas.lists import (
    ExtraItem,
    ExtraItemCreate,
    ExtraItemUpdate,
    ListCopyResult,
    ListCreate,
    ListDetail,
    ListFeedPage,
    ListMealAdd,
    ListMealEaten,
    ListMealEntry,
    ListMealUpdate,
    ListSummary,
    ListUpdate,
)
from app.schemas.users import UserRef
from app.services import (
    access,
    aggregation,
    detach,
    recurring,
    reference,
    shopping,
    walking_order,
)
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
            eaten=content.eaten(list_meal),
            leftover=list_meal.leftover_of_id is not None,
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
        eaten=content.eaten(list_meal),
        leftover=list_meal.leftover_of_id is not None,
    )


def _extra_item(
    content: aggregation.ListContent, row: ListExtraItem, refs: Mapping[str, UserRef]
) -> ExtraItem:
    base_unit = None if row.item_id is None else aggregation.extra_attrs(content, row).base_unit
    return ExtraItem(
        id=row.id,
        item_id=row.item_id,
        text=row.text,
        amount=row.amount,
        unit=None if row.unit is None else Unit(row.unit),
        base_unit=None if base_unit is None else base_unit_name(base_unit),
        unit_fits=base_unit is None or fits(row.amount, row.unit, base_unit),
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
    zone: ZoneInfo,
) -> ListDetail:
    """The list as the viewer sees it, grouped in their walking order (REF-01, D-48); a draft
    they can edit offers their due recurring items (LIST-16), counted in calendar days of
    `zone`."""
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
    owner = owner_key_of(viewer_id, rights.viewer_couple_id)
    lines = aggregation.lines(
        content,
        shopping_list,
        order=await walking_order.order_of(session, owner),
        private_meals=private,
        refs=refs,
    )
    due_items = (
        await recurring.due_items(
            session,
            owner,
            shopping_list.id,
            {line.item_id for line in lines if line.item_id is not None},
            today=local_date(now, zone),
        )
        if shopping_list.status == "draft" and rights.can_edit
        else []
    )
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
        meals=[
            _meal_entry(content, media, row, refs, private=row.id in private, now=now)
            for row in list_meals
        ],
        lines=lines,
        extra_items=[_extra_item(content, row, refs) for row in extras],
        due_items=due_items,
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
    zone: ZoneInfo,
) -> Callable[[], Awaitable[bytes]]:
    """A build of the list's response body for the list cache."""

    async def build() -> bytes:
        detail = await list_detail(
            session, media, viewer_id, shopping_list, rights, now=now, zone=zone
        )
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
    zone: ZoneInfo,
) -> list[CachedList]:
    """The local copy for offline use (SYNC-02): the response bodies of `GET /api/lists/{id}`
    of every list the principal can edit that is a draft or being shopped (their own and those
    their partner shares with them, CPL-02), most recently edited first. Each body comes from
    the list cache (`generation` read before this starts), so the copy costs one detail build
    per list that changed since the last poll or sync of it."""
    async with session.begin():
        couple, partner = await access.couple_and_partner(session, principal.user_id)
        rows = await lists_repo.mine(session, principal.user_id, partner, COPY_STATUSES)
        entries: list[CachedList] = []
        for row in rows:
            rights = ListRights(
                is_owner=row.owner_id == principal.user_id,
                can_edit=True,
                viewer_partner_id=partner,
                viewer_couple_id=couple,
            )
            build = _detail_json(session, media, principal.user_id, row, rights, now=now, zone=zone)
            key = (row.id, principal.user_id, media_urls.expiry(now))
            entries.append(await cache.get_or_build(key, generation, build))
        return entries


async def _new_list(
    session: AsyncSession, principal: Principal, name: str | None, *, now: datetime
) -> tuple[ShoppingList, ListRights]:
    """A new draft of the principal, shared with their partner if they have one (CPL-02), and
    the principal's rights on it."""
    couple, partner = await access.couple_and_partner(session, principal.user_id)
    shopping_list = ShoppingList(
        owner_id=principal.user_id,
        name=name,
        status="draft",
        shared_with_partner=partner is not None,
        version=0,
        created_at=now,
        updated_at=now,
    )
    session.add(shopping_list)
    await session.flush()
    rights = ListRights(
        is_owner=True, can_edit=True, viewer_partner_id=partner, viewer_couple_id=couple
    )
    return shopping_list, rights


async def _add_leftovers(
    session: AsyncSession,
    principal: Principal,
    shopping_list: ShoppingList,
    partner: str | None,
    *,
    now: datetime,
) -> None:
    """Give a new draft the leftovers of the last done list the principal can edit (their own
    or one their partner shares with them), unless it was finished more than `LEFTOVER_DAYS`
    ago: one per meal on it that isn't eaten, leftovers on it included, in its order (LIST-17).
    A leftover copies its source's servings and snapshots and is frozen without rows."""
    source = await lists_repo.last_finished(session, principal.user_id, partner)
    if (
        source is None
        or source.finished_at is None
        or source.finished_at < now - timedelta(days=LEFTOVER_DAYS)
    ):
        return
    meals, sources = await aggregation.shown_meals(session, [source])
    roots: set[str] = set()
    for row in meals.get(source.id, []):
        root = row if row.leftover_of_id is None else sources[row.leftover_of_id]
        if root.eaten or root.id in roots:
            continue
        roots.add(root.id)
        session.add(
            ListMeal(
                list_id=shopping_list.id,
                meal_id=row.meal_id,
                servings=row.servings,
                meal_servings_snapshot=row.meal_servings_snapshot,
                meal_name_snapshot=row.meal_name_snapshot,
                meal_owner_id_snapshot=row.meal_owner_id_snapshot,
                added_by=row.added_by,
                last_added_at=row.last_added_at,
                frozen_at=now,
                detached_reason=row.detached_reason,
                position=len(roots) - 1,
                leftover_of_id=root.id,
                created_at=now,
                updated_at=now,
            )
        )
    await session.flush()


async def create_list(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    body: ListCreate,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListDetail:
    """A new draft (LIST-01), with the leftovers of the last done list (LIST-17)."""
    async with session.begin():
        shopping_list, rights = await _new_list(session, principal, body.name, now=now)
        await _add_leftovers(session, principal, shopping_list, rights.viewer_partner_id, now=now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


async def get_list(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListDetail:
    """A list the principal may see (404 otherwise)."""
    async with session.begin():
        shopping_list, rights = await access.require_list_view(session, principal, list_id)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


async def update_list(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    body: ListUpdate,
    *,
    now: datetime,
    zone: ZoneInfo,
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
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


async def delete_list(
    session: AsyncSession, principal: Principal, list_id: str, *, now: datetime
) -> None:
    """Delete a list in any state (the owner, LIST-13); its content goes with it, and so do the
    leftovers of its meals on other lists, which change (LIST-17)."""
    async with session.begin():
        shopping_list, _ = await access.require_list_owner(session, principal, list_id)
        meal_ids = [row.id for row in (await lists_repo.meals_for(session, [list_id]))[list_id]]
        showing = await lists_repo.lists_with_leftovers_of(session, meal_ids)
        await lists_repo.bump(session, showing - {list_id}, now)
        await session.delete(shopping_list)


async def _copy(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    source: ShoppingList,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListCopyResult:
    """A new draft of the principal from a list: same name, the meals that still exist and
    they may see (the current versions, live again), with their servings, and the extra items
    (unchecked, without snapshots; a free-text item whose category was deleted goes to *Other*,
    LIST-06). `left_out` counts the other meals (VIS-06). Hidden lines and check states are not
    copied (LIST-07). The leftovers it shows come as normal meals, and a meal on it both as a
    leftover and as a normal meal comes once, with both servings; the copy gets no leftovers of
    its own (LIST-17)."""
    visible = await access.visible_owner_ids(session, principal.user_id, "meals")
    list_meals = (await aggregation.shown_meals(session, [source]))[0].get(source.id, [])
    meals = await meals_repo.by_ids(session, (row.meal_id for row in list_meals))
    kept: dict[str, tuple[MealRow, int]] = {}
    left_out = 0
    for row in list_meals:
        meal = None if row.meal_id is None else meals.get(row.meal_id)
        if meal is None or meal.owner_id not in visible:
            left_out += 1
        elif meal.id in kept:
            kept[meal.id] = (meal, raised_servings(kept[meal.id][1], row.servings))
        else:
            kept[meal.id] = (meal, row.servings)
    extras = (await lists_repo.extras_for(session, [source.id]))[source.id]
    copy, rights = await _new_list(session, principal, source.name, now=now)
    for position, (meal, servings) in enumerate(kept.values()):
        session.add(_list_meal(copy, meal, servings, position, principal, now=now))
    for extra in extras:
        session.add(
            ListExtraItem(
                id=new_id(),
                list_id=copy.id,
                item_id=extra.item_id,
                text=extra.text,
                amount=extra.amount,
                unit=extra.unit,
                amount_text=extra.amount_text,
                category_id=(
                    None
                    if extra.category_id is None
                    else await free_text_category_id(session, extra.category_id)
                ),
                added_by=principal.user_id,
                created_at=now,
                updated_at=now,
            )
        )
    await session.flush()
    detail = await list_detail(session, media, principal.user_id, copy, rights, now=now, zone=zone)
    return ListCopyResult(list=detail, left_out=left_out)


async def copy_list(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListCopyResult:
    """Copy a list the principal may see, in any state, into a new draft of theirs
    (VIS-03)."""
    async with session.begin():
        source, _ = await access.require_list_view(session, principal, list_id)
        return await _copy(session, media, principal, source, now=now, zone=zone)


async def shop_again(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListCopyResult:
    """ "Shop again" (SHOP-06): a done list the principal may see (409 `list.not_done` for
    others) into a new draft of theirs, as a copy."""
    async with session.begin():
        source, _ = await access.require_list_view(session, principal, list_id)
        _require_done(source)
        return await _copy(session, media, principal, source, now=now, zone=zone)


# --- shopping mode ------------------------------------------------------------------------


async def start_shopping(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListDetail:
    """ "Start shopping" (LIST-10/11) on a draft the principal may edit (409 `list.not_draft`
    otherwise): its meals are frozen and its linked extra items snapshotted, its current lines
    get a state (later ones are `new`)."""
    async with session.begin():
        shopping_list, rights = await access.require_list_edit(session, principal, list_id)
        _require_draft(shopping_list)
        await shopping.start(session, shopping_list, now=now)
        await touch(session, shopping_list, now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


async def reopen_list(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListDetail:
    """ "Reopen" (SHOP-06): a done list the principal may edit goes back to shopping (409
    `list.not_done` for other states), with its check states."""
    async with session.begin():
        shopping_list, rights = await access.require_list_edit(session, principal, list_id)
        _require_done(shopping_list)
        shopping.reopen(shopping_list)
        await touch(session, shopping_list, now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


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
    zone: ZoneInfo,
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
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


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
    zone: ZoneInfo,
) -> ListDetail:
    """Set the servings of a meal on the list (LIST-04), detached meals included; not a
    leftover's (409 `list_meal.leftover`, LIST-17)."""
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        list_meal = await _list_meal_of(session, shopping_list.id, list_meal_id)
        if list_meal.leftover_of_id is not None:
            raise ApiError(ErrorCode.LIST_MEAL_LEFTOVER, status_code=409)
        if list_meal.servings != body.servings:
            list_meal.servings = body.servings
            list_meal.updated_at = now
            await touch(session, shopping_list, now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


async def remove_meal(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    list_meal_id: str,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListDetail:
    """Take a meal off the list, also one that is no longer available (LIST-15); its leftovers
    on other lists go with it, and those lists change (LIST-17)."""
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        list_meal = await _list_meal_of(session, shopping_list.id, list_meal_id)
        showing = await lists_repo.lists_with_leftovers_of(session, [list_meal.id])
        await lists_repo.bump(session, showing - {shopping_list.id}, now)
        await session.delete(list_meal)
        await touch(session, shopping_list, now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


async def set_meal_eaten(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    list_meal_id: str,
    body: ListMealEaten,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListDetail:
    """Mark a meal on a done list eaten, or clear that (SHOP-07, D-55): editors of the list
    only (CPL-03), and only once it is done (409 `list.not_done` in a draft or while shopping).
    It is the one change a done list takes; its lines stay as they are.

    A leftover is marked on any list, and marks its source meal (LIST-17), which needs edit
    rights on the source's list too (403 otherwise, e.g. once the couple ended). That changes
    every list that shows the source: its own and those with a leftover of it, so all are
    bumped."""
    async with session.begin():
        shopping_list, rights = await access.require_list_edit(session, principal, list_id)
        list_meal = await _list_meal_of(session, shopping_list.id, list_meal_id)
        if list_meal.leftover_of_id is None:
            _require_done(shopping_list)
            target = list_meal
        else:
            target = await _source_of(session, list_meal)
            try:
                await access.require_list_edit(session, principal, target.list_id)
            except ApiError as refused:
                raise ApiError(ErrorCode.FORBIDDEN, status_code=403) from refused
        if target.eaten != body.eaten:
            target.eaten = body.eaten
            target.updated_at = now
            showing = {
                target.list_id,
                *await lists_repo.lists_with_leftovers_of(session, [target.id]),
            }
            await lists_repo.bump(session, showing - {shopping_list.id}, now)
            await touch(session, shopping_list, now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


async def _source_of(session: AsyncSession, leftover: ListMeal) -> ListMeal:
    """A leftover's source meal (it goes with its source, so it always has one)."""
    source = (
        None
        if leftover.leftover_of_id is None
        else await session.get(ListMeal, leftover.leftover_of_id)
    )
    if source is None:  # pragma: no cover -- a leftover goes with its source (foreign key)
        raise RuntimeError("a leftover's source meal is missing")
    return source


async def shop_leftover(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    list_meal_id: str,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListDetail:
    """ "Doch einkaufen" (LIST-17): a leftover becomes a normal meal of the list, with its
    servings, live in a draft and frozen at once while shopping, so its rows go on the list; if
    the meal is on the list already, that one gets its servings instead (LIST-04). Either way it
    counts as added by the principal now (MEAL-09). 409 `list_meal.not_leftover` for a normal
    meal, `list_meal.unavailable` once the meal is deleted or the principal may no longer see
    it."""
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        list_meal = await _list_meal_of(session, shopping_list.id, list_meal_id)
        if list_meal.leftover_of_id is None:
            raise ApiError(ErrorCode.LIST_MEAL_NOT_LEFTOVER, status_code=409)
        meal = (
            None if list_meal.meal_id is None else await meals_repo.get(session, list_meal.meal_id)
        )
        if meal is None or not await access.may_view_meals_of(
            session, principal.user_id, meal.owner_id
        ):
            raise ApiError(ErrorCode.LIST_MEAL_UNAVAILABLE, status_code=409)
        existing = await lists_repo.meal_on_list(session, shopping_list.id, meal.id)
        if existing is not None:
            existing.servings = raised_servings(existing.servings, list_meal.servings)
            existing.added_by, existing.last_added_at = principal.user_id, now
            existing.updated_at = now
            await session.delete(list_meal)
        else:
            list_meal.leftover_of_id = None
            list_meal.frozen_at = None
            list_meal.meal_servings_snapshot = meal.servings
            list_meal.meal_name_snapshot = meal.name
            list_meal.added_by, list_meal.last_added_at = principal.user_id, now
            list_meal.updated_at = now
            if shopping_list.status != "draft":
                await session.flush()
                await detach.freeze(session, [list_meal], now=now)
        await touch(session, shopping_list, now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


# --- extra items --------------------------------------------------------------------------


def _create_problems(body: ExtraItemCreate) -> list[FieldProblem]:
    """Exactly one of item and text, and only the fields of that kind (LIST-06)."""
    if body.item_id is None and body.text is None:
        return [_field("text", FieldErrorCode.REQUIRED)]
    if body.item_id is not None and body.text is not None:
        return [_field("text", FieldErrorCode.INVALID)]
    if body.item_id is not None:
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


async def _find_references(
    session: AsyncSession,
    *,
    item_id: str | None,
    category_id: str | None,
    current_category_id: str | None = None,
) -> tuple[list[FieldProblem], Item | None]:
    """Look up the referenced item and category: the problems with an unknown item
    or a category a free-text item can't be put into (a deleted one or *Uncategorized*, LIST-06;
    an item keeps the category it has, even a deleted one), and the item if one was given
    and found."""
    problems = []
    item = None
    if item_id is not None:
        item = await items_repo.get(session, item_id)
        if item is None:
            problems.append(_field("item_id", FieldErrorCode.INVALID))
    if category_id is not None and not await reference.can_pick(
        session, category_id, keeping=current_category_id
    ):
        problems.append(_field("category_id", FieldErrorCode.INVALID))
    return problems, item


def _unit_problems(
    amount: float | None, unit: Unit | str | None, base_unit: BaseUnit | str
) -> list[FieldProblem]:
    """A linked extra item's unit must fit its item's base unit (REF-02, LIST-06)."""
    return [] if fits(amount, unit, base_unit) else [_field("unit", FieldErrorCode.UNIT_MISMATCH)]


async def other_category_id(session: AsyncSession) -> str:
    other = await reference_repo.category_by_key(session, OTHER_CATEGORY)
    if other is None:  # pragma: no cover -- seeded by migration 0003, never deleted (REF-01)
        raise RuntimeError("the 'other' category is missing")
    return other.id


async def free_text_category_id(session: AsyncSession, category_id: str | None) -> str:
    """Where a free-text item that names `category_id` goes when it must not fail (copies,
    ops): there, unless it names none or one it can't be put into (a deleted one, LIST-06),
    then into *Other*."""
    if category_id is not None and await reference.can_pick(session, category_id):
        return category_id
    return await other_category_id(session)


def _stored_unit(amount: float | None, unit: Unit | str | None) -> str | None:
    """An amount without a unit counts as pieces."""
    stored = counted_unit(amount, unit)
    return None if stored is None else stored.value


async def add_extra(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    body: ExtraItemCreate,
    *,
    now: datetime,
    zone: ZoneInfo,
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
                session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
            )
            return detail, False
        problems = _create_problems(body)
        found, item = await _find_references(
            session, item_id=body.item_id, category_id=body.category_id
        )
        problems += found
        if item is not None:
            problems += _unit_problems(body.amount, body.unit, item.base_unit)
        if problems:
            raise validation_error(problems)
        linked = body.item_id is not None
        extra = ListExtraItem(
            id=body.id or new_id(),
            list_id=shopping_list.id,
            item_id=body.item_id,
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
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
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
    zone: ZoneInfo,
) -> ListDetail:
    """Change the fields that were sent; a linked item stays linked and a free-text item
    stays free text (the other kind's fields are refused). While shopping, a linked item
    moved to another item takes that one's snapshot. A linked extra item whose item,
    amount or unit changes needs a unit that fits the base unit it is calculated with: the new
    item's, else its snapshot's or its item's (D-33)."""
    sent = body.model_fields_set
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        extra = await _extra_of(session, shopping_list.id, extra_id)
        linked = extra.item_id is not None
        other_kind = (
            ("text", "amount_text", "category_id") if linked else ("item_id", "amount", "unit")
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
                "item_id": body.item_id or extra.item_id,
                "amount": amount,
                "unit": _stored_unit(amount, unit),
            }
        else:
            values = {
                "text": body.text or extra.text,
                "amount_text": body.amount_text if "amount_text" in sent else extra.amount_text,
                "category_id": body.category_id or extra.category_id,
            }
        found, item = await _find_references(
            session,
            item_id=body.item_id if linked else None,
            category_id=None if linked else body.category_id,
            current_category_id=extra.category_id,
        )
        problems += found
        if linked and not problems and _changed(extra, values):
            moved = values["item_id"] != extra.item_id
            base_unit = await _extra_base_unit(session, extra, item if moved else None)
            problems += _unit_problems(amount, unit, base_unit)
        if problems:
            raise validation_error(problems)
        if _changed(extra, values):
            if linked and values["item_id"] != extra.item_id:
                extra.attrs_snapshot = None
            for name, value in values.items():
                setattr(extra, name, value)
            if shopping_list.status != "draft":
                await shopping.snapshot_extras(session, [extra])
            extra.updated_at = now
            await touch(session, shopping_list, now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


def _changed(extra: ListExtraItem, values: Mapping[str, object]) -> bool:
    return any(getattr(extra, name) != value for name, value in values.items())


async def _extra_base_unit(
    session: AsyncSession, extra: ListExtraItem, moved_to: Item | None
) -> str:
    """The base unit a linked item is calculated with: the item it moves to, else its
    snapshot's, else its item's (LIST-11)."""
    if moved_to is not None:
        return moved_to.base_unit
    if extra.attrs_snapshot is not None:
        return str(extra.attrs_snapshot["base_unit"])
    item = await items_repo.get(session, str(extra.item_id))
    if item is None:  # pragma: no cover -- the foreign key restricts deleting it
        raise RuntimeError("a linked extra item's item is missing")
    return item.base_unit


async def delete_extra(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    extra_id: str,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListDetail:
    """Delete an extra item; a tombstone stays for offline clients (SYNC)."""
    async with session.begin():
        shopping_list, rights = await _editable(session, principal, list_id)
        extra = await _extra_of(session, shopping_list.id, extra_id)
        extra.deleted_at = now
        extra.updated_at = now
        await touch(session, shopping_list, now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


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
    zone: ZoneInfo,
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
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )


# --- due items ----------------------------------------------------------------------------


async def hide_due_item(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    item_id: str,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> ListDetail:
    """Hide a due recurring item on this draft for everyone who sees it (LIST-16; 409
    `list.not_draft` otherwise), by its item (404 for an unknown one). It need not be
    due or recurring now; hiding it again changes nothing. There is no undo."""
    async with session.begin():
        shopping_list, rights = await access.require_list_edit(session, principal, list_id)
        _require_draft(shopping_list)
        if await items_repo.get(session, item_id) is None:
            raise not_found()
        if await lists_repo.get_hidden_due_item(session, shopping_list.id, item_id) is None:
            session.add(
                ListHiddenDueItem(
                    list_id=shopping_list.id,
                    item_id=item_id,
                    hidden_at=now,
                    hidden_by=principal.user_id,
                )
            )
            await touch(session, shopping_list, now)
        return await list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now, zone=zone
        )
