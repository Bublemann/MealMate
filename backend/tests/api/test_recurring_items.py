"""The recurring items of a user or couple: making an ingredient recurring, the set with its
due dates, changing and removing items, and who may see them (LIST-16, D-42, SEC-04).

The fake clock starts at 2026-09-27 12:00 UTC, 14:00 in Berlin, so "today" is 2026-09-27.
"""

import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.main import create_app
from tests.accounts import Account, FakeClock, error, fields, login, make_couple, make_user
from tests.catalog import create_ingredient, summary
from tests.recurring import (
    create_recurring,
    make_recurring,
    notices,
    recurring,
    store_purchases,
    update_recurring,
    updated,
)
from tests.support import ClientFactory, SettingsFactory


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben")


@pytest.fixture
async def carl(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "carl")


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


@pytest.fixture
async def toilet_paper(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Klopapier", base_unit="piece")


# --- create and list ------------------------------------------------------------------------


async def test_a_new_item_was_last_bought_today(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """ "Zuletzt gekauft" defaults to today, and the interval adapts automatically."""
    item = await make_recurring(api, anna, toilet_paper["id"], weeks=4)
    assert item == {
        "id": item["id"],
        "ingredient": summary(toilet_paper),
        "interval": {"value": 4, "unit": "week", "automatic": True},
        "interval_weeks": 4,
        "last_purchased_on": "2026-09-27",
        "due_on": "2026-10-25",
        "days_until_due": 28,
        "due": False,
        "last_amount": None,
    }
    assert await recurring(api, anna) == {"items": [item], "due_count": 0}


async def test_the_set_is_sorted_by_due_date_then_by_name(api: AsyncClient, anna: Account) -> None:
    """Due items first, the most overdue on top; items due on the same day in dictionary
    order ("Äpfel" next to "Apfelsaft", not after "Zitronen"). An item last bought five weeks
    ago with a four-week interval is due at once."""
    for name, weeks, last_purchased_on in (
        ("Zitronen", 4, None),
        ("Spülmittel", 2, date(2026, 9, 20)),
        ("Apfelsaft", 4, None),
        ("Zahnpasta", 1, date(2026, 9, 20)),
        ("Äpfel", 4, None),
        ("Klopapier", 4, date(2026, 8, 23)),
    ):
        ingredient = await create_ingredient(api, anna, name)
        await make_recurring(api, anna, ingredient["id"], weeks, last_purchased_on)

    body = await recurring(api, anna)
    assert [
        (item["ingredient"]["name"], item["due_on"], item["days_until_due"], item["due"])
        for item in body["items"]
    ] == [
        ("Klopapier", "2026-09-20", -7, True),
        ("Zahnpasta", "2026-09-27", 0, True),
        ("Spülmittel", "2026-10-04", 7, False),
        ("Äpfel", "2026-10-25", 28, False),
        ("Apfelsaft", "2026-10-25", 28, False),
        ("Zitronen", "2026-10-25", 28, False),
    ]
    assert body["due_count"] == 2


@pytest.mark.parametrize(
    ("base_unit", "amount", "unit", "shown"),
    [
        ("g", 1.5, "kg", {"value": 1.5, "unit": "kg"}),
        ("ml", 500, "ml", {"value": 500, "unit": "ml"}),
        ("piece", 12, "piece", {"value": 12, "unit": "piece"}),
        ("piece", 12, None, {"value": 12, "unit": "piece"}),
        ("g", 12, None, None),
        ("piece", 1.5, "kg", None),
        ("ml", 2, "kg", None),
    ],
)  # fmt: skip
async def test_the_last_amount_shows_only_while_it_fits(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    base_unit: str,
    amount: float,
    unit: str | None,
    shown: Any,
) -> None:
    """The last purchase's amount comes with the item when its unit fits the ingredient's base
    unit (REF-02); an amount without a unit counts as pieces."""
    ingredient = await create_ingredient(api, anna, "Waschmittel", base_unit=base_unit)
    item = await make_recurring(api, anna, ingredient["id"])
    await store_purchases(app, item["id"], last_amount=amount, last_unit=unit)
    assert (await recurring(api, anna))["items"][0]["last_amount"] == shown


async def test_the_last_amount_follows_the_current_base_unit(
    app: FastAPI, api: AsyncClient, anna: Account
) -> None:
    """A base unit changed after the purchase hides the amount; changed back, it shows again."""
    ingredient = await create_ingredient(api, anna, "Waschpulver", base_unit="g")
    item = await make_recurring(api, anna, ingredient["id"])
    await store_purchases(app, item["id"], last_amount=1.5, last_unit="kg")

    async def last_amount_as(base_unit: str) -> Any:
        response = await api.patch(
            f"/api/ingredients/{ingredient['id']}",
            json={"base_unit": base_unit},
            headers=anna.headers,
        )
        assert response.status_code == 200, response.text
        return (await recurring(api, anna))["items"][0]["last_amount"]

    assert await last_amount_as("piece") is None
    assert await last_amount_as("g") == {"value": 1.5, "unit": "kg"}


# --- field errors ---------------------------------------------------------------------------


async def test_an_ingredient_is_in_a_set_once(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    await make_recurring(api, anna, toilet_paper["id"])
    response = await create_recurring(api, anna, toilet_paper["id"], weeks=2)
    assert response.status_code == 422
    assert fields(response) == {("body", "ingredient_id"): "taken"}
    assert len((await recurring(api, anna))["items"]) == 1


async def test_an_unknown_ingredient_is_invalid(api: AsyncClient, anna: Account) -> None:
    """Every problem the service finds comes in one answer."""
    response = await create_recurring(
        api, anna, "0190c0de-0000-7000-8000-000000000000", last_purchased_on=date(2026, 9, 28)
    )
    assert response.status_code == 422
    assert fields(response) == {
        ("body", "ingredient_id"): "invalid",
        ("body", "last_purchased_on"): "out_of_range",
    }


@pytest.mark.parametrize(
    ("body", "field", "code"),
    [
        ({"interval_weeks": 0}, "interval_weeks", "out_of_range"),
        ({"interval_weeks": 53}, "interval_weeks", "out_of_range"),
        ({"interval_weeks": 2.5}, "interval_weeks", "invalid"),
        ({"last_purchased_on": "2026-09-28"}, "last_purchased_on", "out_of_range"),  # tomorrow
        ({"last_purchased_on": "2024-09-26"}, "last_purchased_on", "out_of_range"),  # 731 days back
        ({"last_purchased_on": "27.09.2026"}, "last_purchased_on", "invalid"),
    ],
)  # fmt: skip
async def test_values_out_of_range_are_refused(
    api: AsyncClient, anna: Account, toilet_paper: Any, body: Any, field: str, code: str
) -> None:
    response = await api.post(
        "/api/recurring-items",
        json={"ingredient_id": toilet_paper["id"], "interval_weeks": 4} | body,
        headers=anna.headers,
    )
    assert response.status_code == 422
    assert fields(response) == {("body", field): code}
    assert (await recurring(api, anna))["items"] == []


async def test_the_bounds_are_allowed(api: AsyncClient, anna: Account) -> None:
    """1 and 52 weeks; "zuletzt gekauft" today or 730 days back."""
    soap = await create_ingredient(api, anna, "Seife")
    salt = await create_ingredient(api, anna, "Spülmaschinensalz")
    weekly = await make_recurring(
        api, anna, soap["id"], weeks=1, last_purchased_on=date(2024, 9, 27)
    )
    yearly = await make_recurring(
        api, anna, salt["id"], weeks=52, last_purchased_on=date(2026, 9, 27)
    )
    assert (weekly["interval"], weekly["due_on"]) == (
        {"value": 1, "unit": "week", "automatic": True},
        "2024-10-04",
    )
    assert (yearly["interval"], yearly["due_on"]) == (
        {"value": 52, "unit": "week", "automatic": True},
        "2027-09-26",
    )


# --- change ---------------------------------------------------------------------------------


def schedule(item: Any) -> tuple[Any, int, str]:
    """How the interval reads, the interval in weeks and the due date."""
    return item["interval"], item["interval_weeks"], item["due_on"]


def weeks(value: int, *, automatic: bool) -> dict[str, Any]:
    return {"value": value, "unit": "week", "automatic": automatic}


async def test_a_new_interval_is_set_by_hand(
    app: FastAPI, api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """Set by hand, it serves even once the purchases would give another."""
    item = await make_recurring(api, anna, toilet_paper["id"], weeks=4)
    item = await updated(api, anna, item["id"], interval_weeks=2)
    assert schedule(item) == (weeks(2, automatic=False), 2, "2026-10-11")
    await store_purchases(app, item["id"], measured_intervals=[10, 11])
    assert schedule((await recurring(api, anna))["items"][0]) == schedule(item)


async def test_automatic_serves_the_set_interval_until_two_are_measured(
    app: FastAPI, api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """Switched back to automatic, the typed interval serves until two intervals are measured;
    then their average does, rounded to whole days, half up (10.5 days → 11)."""
    item = await make_recurring(api, anna, toilet_paper["id"], weeks=4)
    await updated(api, anna, item["id"], interval_weeks=3)
    item = await updated(api, anna, item["id"], automatic=True)
    assert schedule(item) == (weeks(3, automatic=True), 3, "2026-10-18")

    await store_purchases(app, item["id"], measured_intervals=[10])
    assert schedule((await recurring(api, anna))["items"][0]) == schedule(item)
    await store_purchases(app, item["id"], measured_intervals=[10, 11])
    assert schedule((await recurring(api, anna))["items"][0]) == (
        weeks(2, automatic=True),
        3,
        "2026-10-08",
    )


async def test_a_new_interval_and_automatic_in_one_change(
    app: FastAPI, api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    item = await make_recurring(api, anna, toilet_paper["id"], weeks=4)
    item = await updated(api, anna, item["id"], interval_weeks=3, automatic=True)
    assert schedule(item) == (weeks(3, automatic=True), 3, "2026-10-18")
    item = await updated(api, anna, item["id"], interval_weeks=5, automatic=False)
    assert schedule(item) == (weeks(5, automatic=False), 5, "2026-11-01")


async def test_automatic_off_alone_keeps_the_interval_that_serves(
    app: FastAPI, api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """The average of [10, 11] (11 days) is frozen as the set interval: later purchases don't
    change it, and the edit pop-up shows it in whole weeks."""
    item = await make_recurring(api, anna, toilet_paper["id"], weeks=4)
    await store_purchases(app, item["id"], measured_intervals=[10, 11])
    item = await updated(api, anna, item["id"], automatic=False)
    assert schedule(item) == (weeks(2, automatic=False), 2, "2026-10-08")
    await store_purchases(app, item["id"], measured_intervals=[10, 11, 30])
    assert schedule((await recurring(api, anna))["items"][0]) == schedule(item)


async def test_a_corrected_last_purchase_moves_the_due_date(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    item = await make_recurring(api, anna, toilet_paper["id"], weeks=4)
    item = await updated(api, anna, item["id"], last_purchased_on="2026-09-01")
    assert (item["last_purchased_on"], item["due_on"], item["days_until_due"], item["due"]) == (
        "2026-09-01",
        "2026-09-29",
        2,
        False,
    )
    assert item["interval"] == weeks(4, automatic=True)
    assert (await recurring(api, anna))["items"] == [item]


async def test_an_empty_change_changes_nothing(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    item = await make_recurring(api, anna, toilet_paper["id"])
    assert await updated(api, anna, item["id"]) == item


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"interval_weeks": 0}, "out_of_range"),
        ({"interval_weeks": 53}, "out_of_range"),
        ({"last_purchased_on": "2026-09-28"}, "out_of_range"),
        ({"last_purchased_on": "2024-09-26"}, "out_of_range"),
        ({"interval_weeks": None}, "invalid"),
        ({"automatic": None}, "invalid"),
        ({"last_purchased_on": None}, "invalid"),
    ],
)  # fmt: skip
async def test_a_change_out_of_range_or_to_null_is_refused(
    api: AsyncClient, anna: Account, toilet_paper: Any, body: Any, code: str
) -> None:
    item = await make_recurring(api, anna, toilet_paper["id"])
    response = await update_recurring(api, anna, item["id"], **body)
    assert response.status_code == 422
    assert fields(response) == {("body", next(iter(body))): code}
    assert (await recurring(api, anna))["items"] == [item]


# --- remove ---------------------------------------------------------------------------------


async def test_a_removed_item_is_gone(api: AsyncClient, anna: Account, toilet_paper: Any) -> None:
    """ "Nicht mehr regelmäßig"; the ingredient can be made recurring again afterwards."""
    item = await make_recurring(api, anna, toilet_paper["id"])
    url = f"/api/recurring-items/{item['id']}"
    assert (await api.delete(url, headers=anna.headers)).status_code == 204
    assert await recurring(api, anna) == {"items": [], "due_count": 0}
    response = await api.delete(url, headers=anna.headers)
    assert (response.status_code, error(response)) == (404, "common.not_found")
    await make_recurring(api, anna, toilet_paper["id"])


# --- who sees what --------------------------------------------------------------------------


async def test_another_users_item_is_not_found(
    api: AsyncClient, anna: Account, carl: Account, toilet_paper: Any
) -> None:
    """Each user has a set of their own (SEC-04): carl neither sees anna's item nor can change
    or remove it, and he makes the same ingredient recurring in his own set."""
    item = await make_recurring(api, anna, toilet_paper["id"])
    url = f"/api/recurring-items/{item['id']}"
    assert await recurring(api, carl) == {"items": [], "due_count": 0}
    for response in (
        await api.patch(url, json={"interval_weeks": 1}, headers=carl.headers),
        await api.delete(url, headers=carl.headers),
        await api.patch(
            "/api/recurring-items/0190c0de-0000-7000-8000-000000000000",
            json={"interval_weeks": 1},
            headers=anna.headers,
        ),
    ):
        assert (response.status_code, error(response)) == (404, "common.not_found")
    assert (await recurring(api, anna))["items"] == [item]

    own = await make_recurring(api, carl, toilet_paper["id"], weeks=2)
    assert (await recurring(api, carl))["items"] == [own]
    assert (await recurring(api, anna))["items"] == [item]


async def test_a_couple_shares_one_set(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, toilet_paper: Any
) -> None:
    """Either partner sees, changes and removes the couple's items (D-42); carl still sees
    none of them."""
    await make_couple(api, anna, ben)
    item = await make_recurring(api, anna, toilet_paper["id"])
    assert await recurring(api, ben) == await recurring(api, anna)

    changed = await updated(api, ben, item["id"], interval_weeks=2)
    assert (await recurring(api, anna))["items"] == [changed]
    response = await create_recurring(api, ben, toilet_paper["id"])
    assert fields(response) == {("body", "ingredient_id"): "taken"}
    assert (await recurring(api, carl))["items"] == []

    url = f"/api/recurring-items/{item['id']}"
    assert (await api.delete(url, headers=ben.headers)).status_code == 204
    assert (await recurring(api, anna))["items"] == []


# --- couples form and end (D-42) -----------------------------------------------------------


def by_id(body: Any) -> dict[str, Any]:
    return {item["id"]: item for item in body["items"]}


async def test_forming_a_couple_combines_both_sets(
    api: AsyncClient, anna: Account, ben: Account
) -> None:
    """For an ingredient both keep, the one bought more recently stays with all its values; on
    a tie the requester's (anna's). The others move as they are."""
    toilet_paper, toothpaste, coffee, milk = [
        (await create_ingredient(api, anna, name))["id"]
        for name in ("Klopapier", "Zahnpasta", "Kaffee", "Milch")
    ]
    await make_recurring(api, anna, toilet_paper, weeks=4, last_purchased_on=date(2026, 9, 1))
    later = await make_recurring(
        api, ben, toilet_paper, weeks=2, last_purchased_on=date(2026, 9, 10)
    )
    tie = await make_recurring(api, anna, toothpaste, weeks=6, last_purchased_on=date(2026, 9, 20))
    await make_recurring(api, ben, toothpaste, weeks=3, last_purchased_on=date(2026, 9, 20))
    newer = await make_recurring(api, anna, coffee, weeks=1, last_purchased_on=date(2026, 9, 25))
    await make_recurring(api, ben, coffee, weeks=5, last_purchased_on=date(2026, 9, 24))
    only_ben = await make_recurring(api, ben, milk, weeks=1)

    await make_couple(api, anna, ben)

    combined = await recurring(api, anna)
    assert by_id(combined) == {item["id"]: item for item in (later, tie, newer, only_ben)}
    assert await recurring(api, ben) == combined


def without_id(item: Any) -> Any:
    return {key: value for key, value in item.items() if key != "id"}


async def test_each_partner_keeps_a_copy_when_the_couple_ends(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, toilet_paper: Any
) -> None:
    """Each copy has all the values of the couple's item, and the two go separate ways."""
    await make_couple(api, anna, ben)
    item = await make_recurring(api, anna, toilet_paper["id"], weeks=4)
    await store_purchases(
        app, item["id"], last_amount=2, last_unit="piece", measured_intervals=[10, 12]
    )
    [item] = (await recurring(api, anna))["items"]

    assert (await api.delete("/api/couple", headers=ben.headers)).status_code == 204

    [annas] = (await recurring(api, anna))["items"]
    [bens] = (await recurring(api, ben))["items"]
    assert without_id(annas) == without_id(bens) == without_id(item)
    assert len({item["id"], annas["id"], bens["id"]}) == 3
    await updated(api, anna, annas["id"], interval_weeks=1)
    assert (await recurring(api, ben))["items"] == [bens]


async def test_the_partner_keeps_the_set_when_a_user_is_deleted(
    api: AsyncClient, anna: Account, ben: Account, admin: Account, toilet_paper: Any
) -> None:
    """Deleting a user ends their couple (ADM-03): the partner keeps a copy."""
    await make_couple(api, anna, ben)
    item = await make_recurring(api, anna, toilet_paper["id"])

    response = await api.delete(f"/api/admin/users/{anna.id}", headers=admin.headers)

    assert response.status_code == 204
    [bens] = (await recurring(api, ben))["items"]
    assert without_id(bens) == without_id(item)


async def test_a_deactivated_partner_changes_nothing(
    api: AsyncClient, anna: Account, ben: Account, admin: Account, toilet_paper: Any
) -> None:
    """The couple stays while ben is deactivated (CPL-07), and so does its set."""
    await make_couple(api, anna, ben)
    item = await make_recurring(api, anna, toilet_paper["id"])

    response = await api.patch(
        f"/api/admin/users/{ben.id}", json={"is_active": False}, headers=admin.headers
    )

    assert response.status_code == 200
    assert (await recurring(api, anna))["items"] == [item]
    assert (await updated(api, anna, item["id"], interval_weeks=2))["interval_weeks"] == 2


# --- ingredients merged (ING-05) -------------------------------------------------------------


async def merge(api: AsyncClient, admin: Account, ingredient_id: str, into_id: str) -> None:
    response = await api.post(
        f"/api/admin/ingredients/{ingredient_id}/merge",
        json={"into_id": into_id},
        headers=admin.headers,
    )
    assert response.status_code == 200, response.text


async def test_a_merge_moves_the_item_to_the_surviving_ingredient(
    api: AsyncClient, anna: Account, admin: Account, toilet_paper: Any
) -> None:
    """Merging "WC-Papier" into "Klopapier" keeps anna's item with all its values; she gets no
    notice."""
    duplicate = await create_ingredient(api, anna, "WC-Papier", base_unit="piece")
    item = await make_recurring(api, anna, duplicate["id"], last_purchased_on=date(2026, 9, 1))

    await merge(api, admin, duplicate["id"], toilet_paper["id"])

    assert (await recurring(api, anna))["items"] == [item | {"ingredient": summary(toilet_paper)}]
    assert (await notices(api, anna))["count"] == 0


async def test_when_a_set_has_both_the_later_purchase_stays(
    api: AsyncClient,
    anna: Account,
    ben: Account,
    carl: Account,
    admin: Account,
    toilet_paper: Any,
) -> None:
    """anna bought "WC-Papier" more recently, so that item stays (now of "Klopapier"); the
    couple ben and carl bought both on one day, so their "Klopapier" item stays (D-42)."""
    duplicate = await create_ingredient(api, anna, "WC-Papier", base_unit="piece")
    await make_couple(api, ben, carl)
    later = await make_recurring(
        api, anna, duplicate["id"], weeks=6, last_purchased_on=date(2026, 9, 20)
    )
    await make_recurring(
        api, anna, toilet_paper["id"], weeks=2, last_purchased_on=date(2026, 9, 10)
    )
    await make_recurring(api, ben, duplicate["id"], weeks=3, last_purchased_on=date(2026, 9, 15))
    tie = await make_recurring(
        api, carl, toilet_paper["id"], weeks=5, last_purchased_on=date(2026, 9, 15)
    )

    await merge(api, admin, duplicate["id"], toilet_paper["id"])

    assert (await recurring(api, anna))["items"] == [later | {"ingredient": summary(toilet_paper)}]
    assert (await recurring(api, ben))["items"] == [tie]
    assert (await notices(api, anna))["count"] == (await notices(api, ben))["count"] == 0


# --- due over time --------------------------------------------------------------------------


async def due_today(api: AsyncClient, user: Account) -> tuple[int, bool, int]:
    """The only item's days until due and due flag, and the set's number of due items."""
    await login(api, user)  # the access token has expired while the clock moved on
    body = await recurring(api, user)
    [item] = body["items"]
    return item["days_until_due"], item["due"], body["due_count"]


async def test_an_item_is_due_from_midnight_in_berlin(
    api: AsyncClient, anna: Account, toilet_paper: Any, clock: FakeClock
) -> None:
    """Bought on 27 September with a one-week interval, it is due from 4 October 00:00 in
    Berlin (22:00 UTC, summer time) and stays due."""
    item = await make_recurring(api, anna, toilet_paper["id"], weeks=1)
    assert item["due_on"] == "2026-10-04"
    clock.advance(days=6, hours=9, minutes=59)  # 3 October, 23:59 in Berlin
    assert await due_today(api, anna) == (1, False, 0)
    clock.advance(minutes=1)
    assert await due_today(api, anna) == (0, True, 1)
    clock.advance(days=3)
    assert await due_today(api, anna) == (-3, True, 1)


async def test_days_are_counted_in_the_instance_time_zone(
    make_settings: SettingsFactory, client_for: ClientFactory, migrated_database: Path
) -> None:
    """With `MEALMATE_TIME_ZONE=UTC`, "today" and the due flag change at midnight UTC."""
    settings = make_settings(time_zone="UTC")
    settings.data_dir.mkdir(parents=True)
    shutil.copyfile(migrated_database, settings.database_path)
    app = create_app(settings)
    clock = app.state.clock = FakeClock()
    async with client_for(app) as api:
        anna = await make_user(app, api, "anna")
        ingredient = await create_ingredient(api, anna, "Klopapier")
        item = await make_recurring(api, anna, ingredient["id"], weeks=1)
        assert item["due_on"] == "2026-10-04"
        clock.advance(days=6, hours=11, minutes=59)  # 3 October, 23:59 UTC
        assert await due_today(api, anna) == (1, False, 0)
        clock.advance(minutes=1)
        assert await due_today(api, anna) == (0, True, 1)
