"""Dates and intervals of recurring items (LIST-16, D-42, MNT-02)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.recurring import (
    DisplayInterval,
    LastPurchase,
    Purchase,
    Schedule,
    add_measured,
    display_interval,
    effective_interval,
    interval_weeks,
    last_purchase_in_range,
    local_date,
    preferred_stays,
    purchase_date,
    record_purchase,
    schedule,
    weeks_to_days,
)

BERLIN = ZoneInfo("Europe/Berlin")


@pytest.mark.parametrize(
    ("at", "zone", "expected"),
    [
        # Summer time (UTC+2) until Sun 2026-10-25: the day starts at 22:00Z.
        (datetime(2026, 9, 27, 12, 0, tzinfo=UTC), BERLIN, date(2026, 9, 27)),
        (datetime(2026, 10, 3, 21, 59, tzinfo=UTC), BERLIN, date(2026, 10, 3)),
        (datetime(2026, 10, 3, 22, 0, tzinfo=UTC), BERLIN, date(2026, 10, 4)),
        # Winter time (UTC+1): the day starts at 23:00Z.
        (datetime(2026, 10, 26, 22, 59, tzinfo=UTC), BERLIN, date(2026, 10, 26)),
        (datetime(2026, 10, 26, 23, 0, tzinfo=UTC), BERLIN, date(2026, 10, 27)),
        (datetime(2026, 10, 3, 22, 0, tzinfo=UTC), ZoneInfo("UTC"), date(2026, 10, 3)),
        (datetime(2026, 10, 3, 3, 0, tzinfo=UTC), ZoneInfo("America/New_York"), date(2026, 10, 2)),
    ],
)  # fmt: skip
def test_local_date_is_the_calendar_day_in_the_zone(
    at: datetime, zone: ZoneInfo, expected: date
) -> None:
    assert local_date(at, zone) == expected


@pytest.mark.parametrize(
    ("set_days", "manual", "measured", "expected"),
    [
        # Fewer than two measured intervals: the typed interval serves.
        (28, False, [], 28),
        (28, False, [35], 28),
        # From two on, the average of the measured ones, rounded to whole days, half up.
        (28, False, [30, 34], 32),
        (28, False, [10, 11], 11),
        (28, False, [10, 10, 11], 10),
        (28, False, [10, 11, 11], 11),
        (28, False, [14, 21, 28], 21),
        # At most the last three count.
        (28, False, [100, 7, 7, 7], 7),
        # Set by hand: the set interval, whatever was measured.
        (14, True, [], 14),
        (14, True, [30, 34], 14),
        (26, True, [30, 34, 35], 26),
    ],
)  # fmt: skip
def test_effective_interval(
    set_days: int, manual: bool, measured: list[int], expected: int
) -> None:
    assert effective_interval(set_days, manual=manual, measured=measured) == expected


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        # Below a week in days.
        (1, (1, "day")), (3, (3, "day")), (6, (6, "day")),
        # From a week on in whole weeks, rounded to the nearest: 10 days are 1.43 weeks.
        (7, (1, "week")), (10, (1, "week")), (11, (2, "week")), (14, (2, "week")),
        (24, (3, "week")), (25, (4, "week")), (28, (4, "week")), (364, (52, "week")),
        (400, (57, "week")),
    ],
)  # fmt: skip
def test_display_interval(days: int, expected: tuple[int, str]) -> None:
    value, unit = expected
    assert display_interval(days, manual=False) == DisplayInterval(value, unit, automatic=True)
    assert display_interval(days, manual=True) == DisplayInterval(value, unit, automatic=False)


@pytest.mark.parametrize(
    ("set_days", "expected"),
    [
        (7, 1), (28, 4), (364, 52),
        # A frozen average need not be whole weeks: the edit pop-up gets the nearest, at least 1.
        (3, 1), (10, 1), (11, 2), (26, 4), (32, 5),
    ],
)  # fmt: skip
def test_interval_weeks_for_the_edit_pop_up(set_days: int, expected: int) -> None:
    assert interval_weeks(set_days) == expected


@pytest.mark.parametrize(
    ("last_purchased_on", "today", "due_on", "days_until_due", "due"),
    [
        # Bought today, every 4 weeks.
        (date(2026, 9, 27), date(2026, 9, 27), date(2026, 10, 25), 28, False),
        # The day before, on the day ("fällig heute"), and a week after.
        (date(2026, 9, 27), date(2026, 10, 24), date(2026, 10, 25), 1, False),
        (date(2026, 9, 27), date(2026, 10, 25), date(2026, 10, 25), 0, True),
        (date(2026, 9, 27), date(2026, 11, 1), date(2026, 10, 25), -7, True),
        # "Zuletzt gekauft" five weeks ago: due at once.
        (date(2026, 8, 23), date(2026, 9, 27), date(2026, 9, 20), -7, True),
        # Across the turn of a year.
        (date(2026, 12, 20), date(2027, 1, 1), date(2027, 1, 17), 16, False),
    ],
)  # fmt: skip
def test_due_date_and_days_until_due(
    last_purchased_on: date, today: date, due_on: date, days_until_due: int, due: bool
) -> None:
    result = schedule(
        interval_days=28,
        manual=False,
        measured=[],
        last_purchased_on=last_purchased_on,
        today=today,
    )
    assert (result.due_on, result.days_until_due, result.due) == (due_on, days_until_due, due)


@pytest.mark.parametrize(
    ("interval_days", "manual", "measured", "expected"),
    [
        # The typed 4 weeks serve until two intervals are measured.
        (28, False, [30], Schedule(DisplayInterval(4, "week", automatic=True), 4,
                                   date(2026, 10, 25), 28, due=False)),
        # Then the average (32 days) sets the due date and reads as about 5 weeks.
        (28, False, [30, 34], Schedule(DisplayInterval(5, "week", automatic=True), 4,
                                       date(2026, 10, 29), 32, due=False)),
        # Set by hand: the set interval, whatever was measured.
        (14, True, [30, 34], Schedule(DisplayInterval(2, "week", automatic=False), 2,
                                      date(2026, 10, 11), 14, due=False)),
        # A frozen average of 4 days reads in days; the edit pop-up offers 1 week.
        (4, True, [4, 4], Schedule(DisplayInterval(4, "day", automatic=False), 1,
                                   date(2026, 10, 1), 4, due=False)),
    ],
)  # fmt: skip
def test_schedule_follows_the_effective_interval(
    interval_days: int, manual: bool, measured: list[int], expected: Schedule
) -> None:
    result = schedule(
        interval_days=interval_days,
        manual=manual,
        measured=measured,
        last_purchased_on=date(2026, 9, 27),
        today=date(2026, 9, 27),
    )
    assert result == expected


@pytest.mark.parametrize(
    ("measured", "previous", "purchased_on", "expected"),
    [
        # "Zuletzt gekauft" counts as the purchase before the first one.
        ([], date(2026, 9, 1), date(2026, 9, 29), [28]),
        # The second purchase measures the second interval: from now on the average applies.
        ([28], date(2026, 9, 29), date(2026, 10, 30), [28, 31]),
        ([28, 31], date(2026, 10, 30), date(2026, 11, 26), [28, 31, 27]),
        # Only the last three are kept.
        ([28, 31, 27], date(2026, 11, 26), date(2026, 12, 3), [31, 27, 7]),
        # A purchase on the same day as the last one adds none, an earlier one neither.
        ([28], date(2026, 9, 29), date(2026, 9, 29), [28]),
        ([28], date(2026, 9, 29), date(2026, 9, 20), [28]),
        ([], date(2026, 9, 29), date(2026, 9, 29), []),
    ],
)  # fmt: skip
def test_add_measured(
    measured: list[int], previous: date, purchased_on: date, expected: list[int]
) -> None:
    before = list(measured)
    assert add_measured(measured, previous=previous, purchased_on=purchased_on) == expected
    assert measured == before


@pytest.mark.parametrize(("weeks", "days"), [(1, 7), (4, 28), (52, 364)])
def test_weeks_to_days(weeks: int, days: int) -> None:
    assert weeks_to_days(weeks) == days


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (date(2026, 9, 27), True),
        (date(2026, 9, 28), False),  # in the future
        (date(2026, 9, 26), True),
        # At most 730 days back ("about two years").
        (date(2024, 9, 27), True),
        (date(2024, 9, 26), False),
    ],
)  # fmt: skip
def test_last_purchase_in_range(value: date, expected: bool) -> None:
    assert last_purchase_in_range(value, today=date(2026, 9, 27)) is expected


@pytest.mark.parametrize(
    ("preferred", "other", "expected"),
    [
        (date(2026, 9, 20), date(2026, 9, 10), True),
        (date(2026, 9, 20), date(2026, 9, 20), True),  # a tie keeps the preferred one
        (date(2026, 9, 10), date(2026, 9, 20), False),  # the one bought more recently stays
    ],
)  # fmt: skip
def test_preferred_stays_unless_the_other_was_bought_later(
    preferred: date, other: date, expected: bool
) -> None:
    assert preferred_stays(preferred, other) is expected


@pytest.mark.parametrize(
    ("checked_at", "now", "expected"),
    [
        # The day of the tap in Berlin, not of the request (an offline finish sent days later).
        (datetime(2026, 9, 27, 12, 0, tzinfo=UTC), datetime(2026, 9, 30, 9, 0, tzinfo=UTC),
         date(2026, 9, 27)),
        (datetime(2026, 9, 27, 22, 30, tzinfo=UTC), datetime(2026, 9, 30, 9, 0, tzinfo=UTC),
         date(2026, 9, 28)),
        # A tap up to five minutes ahead of the server near midnight is still today.
        (datetime(2026, 9, 27, 22, 3, tzinfo=UTC), datetime(2026, 9, 27, 21, 59, tzinfo=UTC),
         date(2026, 9, 27)),
    ],
)  # fmt: skip
def test_purchase_date_is_the_day_of_the_check_off_at_most_today(
    checked_at: datetime, now: datetime, expected: date
) -> None:
    assert purchase_date(checked_at, now=now, zone=BERLIN) == expected


LAST = LastPurchase(on=date(2026, 9, 27), measured=(28,), amount=12, unit="piece", list_id="list-a")


@pytest.mark.parametrize(
    ("purchase", "expected"),
    [
        # A later purchase measures the days since the last one and stores its amount.
        (Purchase(on=date(2026, 10, 20), list_id="list-b", amount=1.5, unit="kg"),
         LastPurchase(on=date(2026, 10, 20), measured=(28, 23), amount=1.5, unit="kg",
                      list_id="list-b")),
        # Without one amount the previous amount stays.
        (Purchase(on=date(2026, 10, 20), list_id="list-b", amount=None, unit=None),
         LastPurchase(on=date(2026, 10, 20), measured=(28, 23), amount=12, unit="piece",
                      list_id="list-b")),
        # The same day: the amount changes, no interval is added.
        (Purchase(on=date(2026, 9, 27), list_id="list-b", amount=6, unit="piece"),
         LastPurchase(on=date(2026, 9, 27), measured=(28,), amount=6, unit="piece",
                      list_id="list-b")),
        # Before the last purchase: nothing changes (a list finished offline, sent late).
        (Purchase(on=date(2026, 9, 26), list_id="list-b", amount=6, unit="piece"), None),
        # The list of the last purchase counts once (Reopen and finish again, a resent batch).
        (Purchase(on=date(2026, 10, 20), list_id="list-a", amount=6, unit="piece"), None),
    ],
)  # fmt: skip
def test_record_purchase(purchase: Purchase, expected: LastPurchase | None) -> None:
    assert record_purchase(LAST, purchase) == expected


def test_record_purchase_keeps_only_three_intervals() -> None:
    last = LastPurchase(
        on=date(2026, 9, 27), measured=(28, 31, 27), amount=None, unit=None, list_id=None
    )
    purchase = Purchase(on=date(2026, 10, 4), list_id="list-b", amount=None, unit=None)
    result = record_purchase(last, purchase)
    assert result is not None
    assert result.measured == (31, 27, 7)
