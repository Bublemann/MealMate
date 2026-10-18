"""Dates and intervals of recurring items (LIST-16, D-42, MNT-02).

A recurring item is an ingredient a user, or a couple together, buys again and again. These
rules take an item's stored values and "today" and say when it is due and how its interval
reads; the services load and store, nothing here does I/O.

Days are calendar days in the instance's time zone (`MEALMATE_TIME_ZONE`), so `today` is
`local_date(now, zone)`, never a UTC date.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo
from typing import Literal

DAYS_PER_WEEK = 7
# The interval a user types, in whole weeks (LIST-16).
WEEKS_MIN = 1
WEEKS_MAX = 52
# "Zuletzt gekauft" is not in the future and at most this many days back ("about two years").
LAST_PURCHASE_MAX_DAYS_BACK = 730

# Only the last three intervals between purchases are kept and averaged (LIST-16).
MEASURED_KEPT = 3
# The average replaces the typed interval once this many intervals are measured: "after two
# purchases", as "zuletzt gekauft" counts as the purchase before the first one.
MEASURED_TO_AVERAGE = 2

# Plain alias (not a `type` statement) so the OpenAPI schema inlines the literal.
IntervalUnit = Literal["day", "week"]


@dataclass(frozen=True)
class DisplayInterval:
    """How an interval reads ("alle ~4 Wochen", "alle 3 Tage"); `automatic` is the "~"."""

    value: int
    unit: IntervalUnit
    automatic: bool


@dataclass(frozen=True)
class Schedule:
    """When an item is due, as of a given day, and how its interval reads.

    `days_until_due` counts from today: 1 is "fällig morgen", 0 "fällig heute", and -3
    "fällig seit 3 Tagen". `interval_weeks` is the set interval for the edit pop-up.
    """

    interval: DisplayInterval
    interval_weeks: int
    due_on: date
    days_until_due: int
    due: bool


def _div_half_up(numerator: int, denominator: int) -> int:
    """`numerator / denominator` rounded to a whole number, .5 up (both positive)."""
    return (2 * numerator + denominator) // (2 * denominator)


def local_date(at: datetime, zone: tzinfo) -> date:
    """The calendar day an aware instant falls on in `zone`."""
    return at.astimezone(zone).date()


def weeks_to_days(weeks: int) -> int:
    """A typed interval in days, as it is stored."""
    return weeks * DAYS_PER_WEEK


def last_purchase_in_range(value: date, *, today: date) -> bool:
    """Whether a typed "zuletzt gekauft" is allowed: not after today, at most 730 days back."""
    return today - timedelta(days=LAST_PURCHASE_MAX_DAYS_BACK) <= value <= today


def effective_interval(set_days: int, *, manual: bool, measured: Sequence[int]) -> int:
    """The interval in days that makes an item due: the set one while it was set by hand or
    fewer than two intervals are measured, else the average of the last three measured ones,
    rounded to whole days, half up (D-42)."""
    if manual or len(measured) < MEASURED_TO_AVERAGE:
        return set_days
    recent = measured[-MEASURED_KEPT:]
    return _div_half_up(sum(recent), len(recent))


def interval_weeks(set_days: int) -> int:
    """The set interval in whole weeks, for the edit pop-up: the nearest, at least 1 (a frozen
    average need not be whole weeks)."""
    return max(1, _div_half_up(set_days, DAYS_PER_WEEK))


def display_interval(days: int, *, manual: bool) -> DisplayInterval:
    """An interval as the app shows it (MNT-02): below a week in days, else in whole weeks,
    rounded to the nearest."""
    if days < DAYS_PER_WEEK:
        return DisplayInterval(days, "day", automatic=not manual)
    return DisplayInterval(interval_weeks(days), "week", automatic=not manual)


def schedule(
    *,
    interval_days: int,
    manual: bool,
    measured: Sequence[int],
    last_purchased_on: date,
    today: date,
) -> Schedule:
    """An item is due on its last purchase date plus its effective interval, and stays due from
    that day on until it is bought again (LIST-16)."""
    days = effective_interval(interval_days, manual=manual, measured=measured)
    due_on = last_purchased_on + timedelta(days=days)
    return Schedule(
        interval=display_interval(days, manual=manual),
        interval_weeks=interval_weeks(interval_days),
        due_on=due_on,
        days_until_due=(due_on - today).days,
        due=due_on <= today,
    )


def add_measured(measured: Sequence[int], *, previous: date, purchased_on: date) -> list[int]:
    """The measured intervals after a purchase: the days since the previous purchase are added
    and only the last three kept. "Zuletzt gekauft" counts as the previous purchase for the
    first one. A purchase on the previous purchase's day, or before it, adds none."""
    if purchased_on <= previous:
        return list(measured)
    return [*measured, (purchased_on - previous).days][-MEASURED_KEPT:]


def preferred_stays(preferred: date, other: date) -> bool:
    """When one set would hold two items of one ingredient, the one bought more recently stays,
    with all its values; on a tie the preferred one: the requester's when a couple forms, the
    surviving ingredient's on a merge (D-42). Takes the two last purchase dates."""
    return preferred >= other


def purchase_date(checked_at: datetime, *, now: datetime, zone: tzinfo) -> date:
    """The day a checked line was bought: the calendar day of its check-off in `zone`, not of
    the request that brought it (a list finished offline counts on the right day), and never
    after today (a tap may run up to five minutes ahead of the server, past midnight)."""
    return min(local_date(checked_at, zone), local_date(now, zone))


@dataclass(frozen=True)
class LastPurchase:
    """What a recurring item keeps of its purchases: the last one's day, amount and unit (when
    it was one amount) and list, and the last three intervals between purchases."""

    on: date
    measured: tuple[int, ...]
    amount: float | None
    unit: str | None
    list_id: str | None


@dataclass(frozen=True)
class Purchase:
    """A checked line of the item's ingredient on a finished list (LIST-16): its day, its list,
    and its amount and unit when the line shows exactly one amount."""

    on: date
    list_id: str
    amount: float | None
    unit: str | None


def record_purchase(last: LastPurchase, purchase: Purchase) -> LastPurchase | None:
    """The item after a purchase, or None when it changes nothing (LIST-16, D-42): a list counts
    once (finished again after "Reopen", a batch sent twice), and a purchase before the last one
    is ignored (a list finished offline and sent late). A purchase on the last one's day takes
    its amount but adds no interval; one without an amount keeps the previous amount."""
    if purchase.list_id == last.list_id or purchase.on < last.on:
        return None
    measured = add_measured(last.measured, previous=last.on, purchased_on=purchase.on)
    amount, unit = (
        (last.amount, last.unit) if purchase.amount is None else (purchase.amount, purchase.unit)
    )
    return LastPurchase(
        on=purchase.on, measured=tuple(measured), amount=amount, unit=unit, list_id=purchase.list_id
    )
