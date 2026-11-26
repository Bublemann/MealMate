"""Recurring items (LIST-16, D-42): the caller's set, making an item recurring, changing
and removing items, and the purchases finished lists record.

A user sees and changes one set: their couple's while they are in one, else their own
(`access.owner_key`). When an item is due and how its interval reads follow from
`domain.recurring`, counted in calendar days of the instance's time zone.

`services.hooks` must not import this module: it imports `services.items`, which imports
the hooks. `services.ops` and `services.lists` import it, so it must not import them.
"""

from collections.abc import Collection
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldErrorCode, FieldProblem, validation_error
from app.domain import recurring
from app.domain.owners import OwnerKey
from app.domain.units import counted_unit, fits
from app.domain.walking_order import ADMINS_ORDER
from app.models import Item as ItemRow
from app.models import RecurringItem as RecurringItemRow
from app.models import ShoppingList
from app.repositories import items as items_repo
from app.repositories import recurring as recurring_repo
from app.schemas.lists import DisplayAmountOut, DueItem, ListLine
from app.schemas.recurring import (
    RecurringInterval,
    RecurringItem,
    RecurringItemCreate,
    RecurringItemList,
    RecurringItemUpdate,
)
from app.services import access, aggregation
from app.services.items import summary as item_summary
from app.services.principal import Principal


def _field(name: str, code: FieldErrorCode) -> FieldProblem:
    return FieldProblem(("body", name), code)


def _last_purchase_problems(value: date, *, today: date) -> list[FieldProblem]:
    """A typed last purchase date ("zuletzt gekauft") is not in the future and at most 730
    days back."""
    if recurring.last_purchase_in_range(value, today=today):
        return []
    return [_field("last_purchased_on", FieldErrorCode.OUT_OF_RANGE)]


def _set_interval(recurring_item: RecurringItemRow, body: RecurringItemUpdate) -> None:
    """A new interval is set by hand, unless `automatic` is sent true with it. `automatic`
    false alone keeps the interval that serves now as the set one; an average need not be whole
    weeks."""
    if body.interval_weeks is not None:
        recurring_item.interval_days = recurring.weeks_to_days(body.interval_weeks)
    elif body.automatic is False:
        recurring_item.interval_days = recurring.effective_interval(
            recurring_item.interval_days,
            manual=recurring_item.interval_manual,
            measured=recurring_item.measured_intervals,
        )
    if body.automatic is not None:
        recurring_item.interval_manual = not body.automatic
    elif body.interval_weeks is not None:
        recurring_item.interval_manual = True


def _last_amount(recurring_item: RecurringItemRow, base_unit: str) -> DisplayAmountOut | None:
    """The last purchase's amount, only while it fits the item's base unit (REF-02)."""
    amount, unit = (
        recurring_item.last_amount,
        counted_unit(recurring_item.last_amount, recurring_item.last_unit),
    )
    if amount is None or unit is None or not fits(amount, unit, base_unit):
        return None
    return DisplayAmountOut(value=amount, unit=unit)


def _view(recurring_item: RecurringItemRow, item: ItemRow, today: date) -> RecurringItem:
    plan = recurring.schedule(
        interval_days=recurring_item.interval_days,
        manual=recurring_item.interval_manual,
        measured=recurring_item.measured_intervals,
        last_purchased_on=recurring_item.last_purchased_on,
        today=today,
    )
    return RecurringItem(
        id=recurring_item.id,
        ingredient=item_summary(item),
        interval=RecurringInterval(
            value=plan.interval.value, unit=plan.interval.unit, automatic=plan.interval.automatic
        ),
        interval_weeks=plan.interval_weeks,
        last_purchased_on=recurring_item.last_purchased_on,
        due_on=plan.due_on,
        days_until_due=plan.days_until_due,
        due=plan.due,
        last_amount=_last_amount(recurring_item, item.base_unit),
    )


async def list_items(
    session: AsyncSession, principal: Principal, *, now: datetime, zone: ZoneInfo
) -> RecurringItemList:
    """The caller's set, sorted by due date and then by the item's name and brand."""
    async with session.begin():
        key = await access.owner_key(session, principal.user_id)
        rows = await recurring_repo.of_owner(session, key)
    today = recurring.local_date(now, zone)
    # The rows come in dictionary order, which the stable sort keeps within a due date.
    recurring_items = sorted(
        (_view(recurring_item, item, today) for recurring_item, item in rows),
        key=lambda recurring_item: recurring_item.due_on,
    )
    return RecurringItemList(
        items=recurring_items,
        due_count=sum(recurring_item.due for recurring_item in recurring_items),
    )


async def due_items(
    session: AsyncSession,
    key: OwnerKey,
    list_id: str,
    on_list: Collection[str],
    *,
    today: date,
) -> list[DueItem]:
    """The "Fällig" box of a draft (LIST-16): the due items of the owner's set that weren't
    hidden on the list and whose item is not in `on_list` (the item ids of its
    lines, hidden ones included), the most overdue first, then in dictionary order. One
    query."""
    rows = await recurring_repo.of_owner(session, key, not_hidden_on=list_id)
    views = [
        _view(recurring_item, item, today)
        for recurring_item, item in rows
        if recurring_item.item_id not in on_list
    ]
    # The rows come in dictionary order, which the stable sort keeps within a day.
    due = sorted((view for view in views if view.due), key=lambda view: view.days_until_due)
    return [
        DueItem(
            ingredient=view.ingredient,
            due_on=view.due_on,
            days_until_due=view.days_until_due,
            last_purchased_on=view.last_purchased_on,
            last_amount=view.last_amount,
        )
        for view in due
    ]


async def create_item(
    session: AsyncSession,
    principal: Principal,
    body: RecurringItemCreate,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> RecurringItem:
    """Make an item recurring in the caller's set: 422 `taken` if the set has it,
    `invalid` if it doesn't exist, `out_of_range` for a last purchase date not allowed."""
    today = recurring.local_date(now, zone)
    last_purchased_on = body.last_purchased_on or today
    async with session.begin():
        key = await access.owner_key(session, principal.user_id)
        item = await items_repo.get(session, body.ingredient_id)
        problems = _last_purchase_problems(last_purchased_on, today=today)
        if item is None:
            problems.append(_field("ingredient_id", FieldErrorCode.INVALID))
        elif await recurring_repo.in_set(session, key, item.id) is not None:
            problems.append(_field("ingredient_id", FieldErrorCode.TAKEN))
        if item is None or problems:
            raise validation_error(problems)
        recurring_item = RecurringItemRow(
            couple_id=key.couple_id,
            user_id=key.user_id,
            item_id=item.id,
            interval_days=recurring.weeks_to_days(body.interval_weeks),
            interval_manual=False,
            last_purchased_on=last_purchased_on,
            measured_intervals=[],
            created_at=now,
            updated_at=now,
        )
        session.add(recurring_item)
        await session.flush()
        return _view(recurring_item, item, today)


async def _item_of(session: AsyncSession, recurring_item: RecurringItemRow) -> ItemRow:
    item = await items_repo.get(session, recurring_item.item_id)
    if item is None:  # pragma: no cover -- deleting it deletes its recurring items
        raise RuntimeError("a recurring item's item is missing")
    return item


async def update_item(
    session: AsyncSession,
    principal: Principal,
    recurring_id: str,
    body: RecurringItemUpdate,
    *,
    now: datetime,
    zone: ZoneInfo,
) -> RecurringItem:
    """Change the interval or correct the last purchase date of an item in the caller's set
    (404 for any other)."""
    today = recurring.local_date(now, zone)
    last_purchased_on = body.last_purchased_on
    async with session.begin():
        recurring_item = await access.require_recurring_item(session, principal, recurring_id)
        if last_purchased_on is not None and (
            problems := _last_purchase_problems(last_purchased_on, today=today)
        ):
            raise validation_error(problems)
        before = (
            recurring_item.interval_days,
            recurring_item.interval_manual,
            recurring_item.last_purchased_on,
        )
        _set_interval(recurring_item, body)
        if last_purchased_on is not None:
            recurring_item.last_purchased_on = last_purchased_on
        if (
            recurring_item.interval_days,
            recurring_item.interval_manual,
            recurring_item.last_purchased_on,
        ) != before:
            recurring_item.updated_at = now
        return _view(recurring_item, await _item_of(session, recurring_item), today)


async def delete_item(session: AsyncSession, principal: Principal, recurring_id: str) -> None:
    """Remove an item from the caller's set ("Nicht mehr regelmäßig"; 404 for any other)."""
    async with session.begin():
        recurring_item = await access.require_recurring_item(session, principal, recurring_id)
        await session.delete(recurring_item)


def _purchase(line: ListLine, list_id: str, *, now: datetime, zone: ZoneInfo) -> recurring.Purchase:
    """A checked line as a purchase: dated by its check-off, with its amount when it shows
    exactly one ("12 Stk.", not "500 g + 2 Stk." nor only parts without an amount)."""
    if line.checked_at is None:  # pragma: no cover -- a checked line has its tap time
        raise RuntimeError("a checked line has no check-off time")
    amount = line.amounts[0] if len(line.amounts) == 1 else None
    return recurring.Purchase(
        on=recurring.purchase_date(line.checked_at, now=now, zone=zone),
        list_id=list_id,
        amount=None if amount is None else amount.value,
        unit=None if amount is None else amount.unit.value,
    )


async def record_purchases(
    session: AsyncSession, shopping_list: ShoppingList, *, now: datetime, zone: ZoneInfo
) -> None:
    """Record the purchases of a done list (LIST-16): each line the list shows as checked (a
    line that needs more since doesn't count) of an item in the set of the list's owner,
    their couple's while in one, so a partner's finish counts for the same set (CPL-03).
    Free-text lines never count. `domain.recurring.record_purchase` decides what changes: a
    list counts once and nothing goes backwards, so this may run again for the same list."""
    key = await access.owner_key(session, shopping_list.owner_id)
    recurring_items = {
        recurring_item.item_id: recurring_item
        for recurring_item, _ in await recurring_repo.of_owner(session, key)
    }
    if not recurring_items:
        return
    content = await aggregation.load(session, [shopping_list])
    lines = aggregation.lines(content, shopping_list, order=ADMINS_ORDER, private_meals=(), refs={})
    for line in lines:
        recurring_item = (
            None if line.ingredient_id is None else recurring_items.get(line.ingredient_id)
        )
        if recurring_item is None or not line.checked:
            continue
        after = recurring.record_purchase(
            recurring.LastPurchase(
                on=recurring_item.last_purchased_on,
                measured=tuple(recurring_item.measured_intervals),
                amount=recurring_item.last_amount,
                unit=recurring_item.last_unit,
                list_id=recurring_item.last_list_id,
            ),
            _purchase(line, shopping_list.id, now=now, zone=zone),
        )
        if after is None:
            continue
        recurring_item.last_purchased_on, recurring_item.measured_intervals = (
            after.on,
            list(after.measured),
        )
        recurring_item.last_amount, recurring_item.last_unit = after.amount, after.unit
        recurring_item.last_list_id, recurring_item.updated_at = after.list_id, now
