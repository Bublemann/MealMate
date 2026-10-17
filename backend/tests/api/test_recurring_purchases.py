"""Purchases of recurring items: checked lines on finished lists move an item's last purchase,
amount and interval, once per list and never backwards (LIST-16, D-42, SYNC-04/05/06,
SHOP-06, CPL-03).

The fake clock starts at 2026-09-27 12:00 UTC, 14:00 in Berlin, so "today" is 2026-09-27.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.accounts import START, Account, FakeClock, login, make_couple, make_user
from tests.catalog import create_ingredient
from tests.lists import (
    applied,
    by_key,
    check,
    create_list,
    extra_added,
    op,
    results,
    send_ops,
    start_shopping,
)
from tests.recurring import make_recurring, recurring, store_purchases, updated

MINUTE = timedelta(minutes=1)


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben")


@pytest.fixture
async def toilet_paper(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Klopapier", base_unit="piece")


@pytest.fixture
async def soap(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Seife", base_unit="piece")


def key(ingredient: Any) -> str:
    return f"i:{ingredient['id']}"


async def item_of(api: AsyncClient, user: Account, ingredient: Any) -> Any:
    """The user's recurring item of the ingredient, as `GET /api/recurring-items` shows it."""
    body = await recurring(api, user)
    return next(item for item in body["items"] if item["ingredient"]["id"] == ingredient["id"])


async def shopping_with(api: AsyncClient, user: Account, *extras: dict[str, Any]) -> Any:
    """A new list of the user with these extra items, being shopped."""
    shopping_list = await create_list(api, user)
    for extra in extras:
        await extra_added(api, user, shopping_list["id"], **extra)
    return await start_shopping(api, user, shopping_list["id"])


# --- what a purchase records ----------------------------------------------------------------


async def test_a_checked_line_on_a_finished_list_is_a_purchase(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """The purchase is dated by the check-off and stores the line's one amount."""
    await make_recurring(
        api, anna, toilet_paper["id"], weeks=4, last_purchased_on=date(2026, 8, 23)
    )
    shopping_list = await shopping_with(
        api, anna, {"ingredient_id": toilet_paper["id"], "amount": 12, "unit": "piece"}
    )
    await applied(
        api,
        anna,
        shopping_list["id"],
        check(key(toilet_paper), at=START),
        op("list.finish", at=START + timedelta(minutes=1)),
    )

    item = await item_of(api, anna, toilet_paper)
    assert item["last_purchased_on"] == "2026-09-27"
    assert item["last_amount"] == {"value": 12, "unit": "piece"}
    assert (item["due_on"], item["due"]) == ("2026-10-25", False)


async def test_a_finish_sent_days_later_keeps_the_day_of_the_check_off(
    api: AsyncClient, anna: Account, toilet_paper: Any, clock: FakeClock
) -> None:
    """A list finished offline reaches the server three days later from the outbox (SYNC-04);
    the purchase still counts on the day of the tap in Berlin, not on its UTC date."""
    await make_recurring(
        api, anna, toilet_paper["id"], weeks=4, last_purchased_on=date(2026, 8, 23)
    )
    shopping_list = await shopping_with(api, anna, {"ingredient_id": toilet_paper["id"]})
    tap = START + timedelta(hours=10, minutes=30)  # 00:30 in Berlin on 09-28, 22:30Z on 09-27
    clock.advance(days=3)
    await login(api, anna)
    await applied(
        api,
        anna,
        shopping_list["id"],
        check(key(toilet_paper), at=tap),
        op("list.finish", at=tap + timedelta(minutes=1)),
    )

    item = await item_of(api, anna, toilet_paper)
    assert item["last_purchased_on"] == "2026-09-28"


async def finished(api: AsyncClient, user: Account, list_id: str, *checked: Any, at: Any) -> Any:
    """Check the lines off at `at` and finish a minute later; the list afterwards."""
    ops = [check(key(ingredient), at=at) for ingredient in checked]
    return await applied(api, user, list_id, *ops, op("list.finish", at=at + MINUTE))


async def test_a_line_without_one_amount_keeps_the_previous_amount(
    app: FastAPI, api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    item = await make_recurring(api, anna, toilet_paper["id"], last_purchased_on=date(2026, 8, 23))
    await store_purchases(app, item["id"], last_amount=8, last_unit="piece")
    shopping_list = await shopping_with(api, anna, {"ingredient_id": toilet_paper["id"]})
    await finished(api, anna, shopping_list["id"], toilet_paper, at=START)

    item = await item_of(api, anna, toilet_paper)
    assert item["last_purchased_on"] == "2026-09-27"
    assert item["last_amount"] == {"value": 8, "unit": "piece"}


# --- whose purchases count ------------------------------------------------------------------


async def test_a_partners_finish_counts_for_the_couples_set(
    api: AsyncClient, anna: Account, ben: Account, toilet_paper: Any, soap: Any
) -> None:
    """ben finishing anna's shared list, or his own, buys for the couple's one set (CPL-03)."""
    await make_couple(api, anna, ben)
    await make_recurring(api, anna, toilet_paper["id"], last_purchased_on=date(2026, 8, 23))
    await make_recurring(api, ben, soap["id"], last_purchased_on=date(2026, 8, 23))
    shared = await shopping_with(api, anna, {"ingredient_id": toilet_paper["id"]})
    await finished(api, ben, shared["id"], toilet_paper, at=START)
    own = await shopping_with(api, ben, {"ingredient_id": soap["id"], "amount": 3})
    await finished(api, ben, own["id"], soap, at=START)

    for user in (anna, ben):
        assert [
            (item["ingredient"]["name"], item["last_purchased_on"])
            for item in (await recurring(api, user))["items"]
        ] == [("Klopapier", "2026-09-27"), ("Seife", "2026-09-27")]
    assert (await item_of(api, anna, soap))["last_amount"] == {"value": 3, "unit": "piece"}


async def test_unchecked_and_free_text_lines_and_unfinished_lists_count_nothing(
    api: AsyncClient, anna: Account, toilet_paper: Any, soap: Any
) -> None:
    """Only checked lines of a recurring ingredient on a finished list are purchases; a free-
    text "Klopapier" is no ingredient, and a list being shopped is not finished yet."""
    for ingredient in (toilet_paper, soap):
        await make_recurring(api, anna, ingredient["id"], last_purchased_on=date(2026, 8, 23))
    before = await recurring(api, anna)
    shopping_list = await shopping_with(
        api, anna, {"ingredient_id": toilet_paper["id"]}, {"ingredient_id": soap["id"]},
        {"text": "Klopapier"},
    )  # fmt: skip
    text_key = next(line["key"] for line in shopping_list["lines"] if line["kind"] == "text")
    list_id = shopping_list["id"]
    await applied(api, anna, list_id, check(key(toilet_paper), at=START), check(text_key, at=START))
    assert await recurring(api, anna) == before  # not finished

    await applied(api, anna, list_id, op("list.finish", at=START + MINUTE))
    assert (await item_of(api, anna, toilet_paper))["last_purchased_on"] == "2026-09-27"
    assert (await item_of(api, anna, soap))["last_purchased_on"] == "2026-08-23"


async def test_a_line_that_needs_more_was_not_bought(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """A checked line whose amount grew since shows unchecked on the done list (LIST-12), so
    it is no purchase."""
    await make_recurring(api, anna, toilet_paper["id"], last_purchased_on=date(2026, 8, 23))
    shopping_list = await shopping_with(
        api, anna, {"ingredient_id": toilet_paper["id"], "amount": 8}
    )
    list_id = shopping_list["id"]
    await applied(api, anna, list_id, check(key(toilet_paper), at=START))
    await extra_added(api, anna, list_id, ingredient_id=toilet_paper["id"], amount=4)
    body = await applied(api, anna, list_id, op("list.finish", at=START + MINUTE))
    assert by_key(body, key(toilet_paper))["needs_more"] is not None

    assert (await item_of(api, anna, toilet_paper))["last_purchased_on"] == "2026-08-23"


# --- once, and never backwards (SYNC-05, SYNC-06, SHOP-06) ----------------------------------


async def test_a_late_check_off_on_a_done_list_is_a_purchase_too(
    api: AsyncClient, anna: Account, ben: Account, toilet_paper: Any, soap: Any, clock: FakeClock
) -> None:
    """anna checked soap off before ben finished, but her phone sends it afterwards (SYNC-06):
    it counts, and toilet paper, bought with the finish, doesn't count again."""
    await make_couple(api, anna, ben)
    for ingredient in (toilet_paper, soap):
        await make_recurring(api, anna, ingredient["id"], last_purchased_on=date(2026, 8, 23))
    shopping_list = await shopping_with(
        api, anna, {"ingredient_id": toilet_paper["id"]}, {"ingredient_id": soap["id"]}
    )
    clock.advance(minutes=20)
    for user in (anna, ben):
        await login(api, user)
    await finished(api, ben, shopping_list["id"], toilet_paper, at=START + 10 * MINUTE)
    bought = await item_of(api, anna, toilet_paper)

    await applied(api, anna, shopping_list["id"], check(key(soap), at=START + 5 * MINUTE))
    assert (await item_of(api, anna, soap))["last_purchased_on"] == "2026-09-27"
    assert await item_of(api, anna, toilet_paper) == bought


async def test_a_list_counts_once(
    api: AsyncClient, anna: Account, toilet_paper: Any, clock: FakeClock
) -> None:
    """Finishing again after "Reopen", with the line checked off anew three days later, and
    sending the same batch twice, count nothing twice."""
    await make_recurring(api, anna, toilet_paper["id"], last_purchased_on=date(2026, 8, 28))
    shopping_list = await shopping_with(api, anna, {"ingredient_id": toilet_paper["id"]})
    list_id = shopping_list["id"]
    batch = [check(key(toilet_paper), at=START), op("list.finish", at=START + MINUTE)]
    await applied(api, anna, list_id, *batch)
    bought = await item_of(api, anna, toilet_paper)
    assert (bought["last_purchased_on"], bought["due_on"]) == ("2026-09-27", "2026-10-25")

    assert results(await send_ops(api, anna, list_id, *batch)) == [("duplicate", None)] * 2
    clock.advance(days=3)
    await login(api, anna)
    reopened = await api.post(f"/api/lists/{list_id}/reopen", headers=anna.headers)
    assert reopened.status_code == 200, reopened.text
    later = clock.now
    await applied(
        api,
        anna,
        list_id,
        check(key(toilet_paper), False, at=later),
        check(key(toilet_paper), at=later + MINUTE),
        op("list.finish", at=later + 2 * MINUTE),
    )
    assert await item_of(api, anna, toilet_paper) == bought | {"days_until_due": 25}


async def test_a_purchase_before_the_last_one_changes_nothing(
    api: AsyncClient, anna: Account, toilet_paper: Any, clock: FakeClock
) -> None:
    """List A was finished offline on day 0 and is sent after list B was finished on day 2:
    the last purchase stays on day 2, with B's amount."""
    await make_recurring(api, anna, toilet_paper["id"], last_purchased_on=date(2026, 8, 23))
    offline = await shopping_with(api, anna, {"ingredient_id": toilet_paper["id"], "amount": 4})
    clock.advance(days=2)
    await login(api, anna)
    online = await shopping_with(api, anna, {"ingredient_id": toilet_paper["id"], "amount": 8})
    await finished(api, anna, online["id"], toilet_paper, at=clock.now)
    bought = await item_of(api, anna, toilet_paper)
    assert bought["last_purchased_on"] == "2026-09-29"

    await finished(api, anna, offline["id"], toilet_paper, at=START)
    assert await item_of(api, anna, toilet_paper) == bought
    assert bought["last_amount"] == {"value": 8, "unit": "piece"}


async def test_a_second_purchase_on_the_same_day_adds_no_interval(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """The amount is the new one; an interval of 0 days would have halved the average."""
    await make_recurring(api, anna, toilet_paper["id"], last_purchased_on=date(2026, 8, 28))
    for amount in (4, 8):
        shopping_list = await shopping_with(
            api, anna, {"ingredient_id": toilet_paper["id"], "amount": amount}
        )
        await finished(api, anna, shopping_list["id"], toilet_paper, at=START)

    item = await item_of(api, anna, toilet_paper)
    assert (item["last_purchased_on"], item["due_on"]) == ("2026-09-27", "2026-10-25")
    assert item["last_amount"] == {"value": 8, "unit": "piece"}


async def test_a_late_uncheck_undoes_no_purchase(
    api: AsyncClient, anna: Account, toilet_paper: Any, clock: FakeClock
) -> None:
    """An uncheck tapped before the finish but sent after it is applied (SYNC-06); the
    purchase stays."""
    await make_recurring(api, anna, toilet_paper["id"], last_purchased_on=date(2026, 8, 23))
    shopping_list = await shopping_with(api, anna, {"ingredient_id": toilet_paper["id"]})
    clock.advance(minutes=10)
    await login(api, anna)
    await finished(api, anna, shopping_list["id"], toilet_paper, at=START)
    bought = await item_of(api, anna, toilet_paper)

    body = await applied(
        api, anna, shopping_list["id"], check(key(toilet_paper), False, at=START + MINUTE / 2)
    )
    assert by_key(body, key(toilet_paper))["checked"] is False
    assert await item_of(api, anna, toilet_paper) == bought


# --- the interval ---------------------------------------------------------------------------


async def test_after_the_second_purchase_the_interval_is_the_average(
    api: AsyncClient, anna: Account, toilet_paper: Any, soap: Any, clock: FakeClock
) -> None:
    """Both were last bought 30 days ago, every 4 weeks; then bought today and 20 days later.
    The measured intervals 30 and 20 average 25 days for toilet paper; soap's interval, set by
    hand, stays 28 days."""
    for ingredient in (toilet_paper, soap):
        await make_recurring(api, anna, ingredient["id"], last_purchased_on=date(2026, 8, 28))
    manual = await item_of(api, anna, soap)
    await updated(api, anna, manual["id"], interval_weeks=4)
    first = await shopping_with(
        api, anna, {"ingredient_id": toilet_paper["id"]}, {"ingredient_id": soap["id"]}
    )
    await finished(api, anna, first["id"], toilet_paper, soap, at=START)
    once = await item_of(api, anna, toilet_paper)
    assert (once["due_on"], once["interval"]) == (
        "2026-10-25",
        {"value": 4, "unit": "week", "automatic": True},
    )

    clock.advance(days=20)
    await login(api, anna)
    second = await shopping_with(
        api, anna, {"ingredient_id": toilet_paper["id"]}, {"ingredient_id": soap["id"]}
    )
    await finished(api, anna, second["id"], toilet_paper, soap, at=clock.now)
    automatic = await item_of(api, anna, toilet_paper)
    assert (automatic["last_purchased_on"], automatic["due_on"]) == ("2026-10-17", "2026-11-11")
    assert automatic["interval"] == {"value": 4, "unit": "week", "automatic": True}
    by_hand = await item_of(api, anna, soap)
    assert (by_hand["due_on"], by_hand["interval"]) == (
        "2026-11-14",
        {"value": 4, "unit": "week", "automatic": False},
    )


async def test_deleting_a_done_list_changes_no_recurring_item(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    await make_recurring(api, anna, toilet_paper["id"], last_purchased_on=date(2026, 8, 23))
    shopping_list = await shopping_with(api, anna, {"ingredient_id": toilet_paper["id"]})
    await finished(api, anna, shopping_list["id"], toilet_paper, at=START)
    bought = await item_of(api, anna, toilet_paper)

    response = await api.delete(f"/api/lists/{shopping_list['id']}", headers=anna.headers)
    assert response.status_code == 204
    assert await item_of(api, anna, toilet_paper) == bought
