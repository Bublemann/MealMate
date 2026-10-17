"""Due recurring items on drafts: the "Fällig" box's entries in the list detail, and hiding one
on a list (LIST-16, D-42, LIST-05, LIST-07, SYNC-08).

The fake clock starts at 2026-09-27 12:00 UTC, 14:00 in Berlin, so "today" is 2026-09-27.
"""

import shutil
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.main import create_app
from app.services.list_cache import ListCache
from tests.accounts import (
    START,
    Account,
    FakeClock,
    error,
    login,
    make_couple,
    make_user,
    set_privacy,
)
from tests.catalog import create_ingredient, summary
from tests.lists import added, applied, by_key, create_list, detail, extra_added, op, start_shopping
from tests.meals import create_meal
from tests.recurring import make_recurring, store_purchases
from tests.support import ClientFactory, SettingsFactory

# Last bought five weeks ago, every four weeks: due since a week.
FIVE_WEEKS_AGO = date(2026, 8, 23)


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
async def toilet_paper(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Klopapier", base_unit="piece")


# --- what a draft offers --------------------------------------------------------------------


async def test_a_due_item_is_offered_on_every_draft_one_can_edit(
    api: AsyncClient, anna: Account, ben: Account, toilet_paper: Any
) -> None:
    """Last bought five weeks ago, every four weeks: due for a week, on anna's draft and on
    the same draft for ben, who shares the set and the list."""
    await make_couple(api, anna, ben)
    await make_recurring(
        api, anna, toilet_paper["id"], weeks=4, last_purchased_on=date(2026, 8, 23)
    )
    draft = await create_list(api, anna)

    expected = [
        {
            "ingredient": summary(toilet_paper),
            "due_on": "2026-09-20",
            "days_until_due": -7,
            "last_purchased_on": "2026-08-23",
            "last_amount": None,
        }
    ]
    assert draft["due_items"] == expected
    assert (await detail(api, ben, draft["id"]))["due_items"] == expected


def offered(list_detail: Any) -> list[str]:
    """The names of the due items the list offers."""
    return [item["ingredient"]["name"] for item in list_detail["due_items"]]


async def test_most_overdue_first_with_the_last_amount_when_it_fits(
    app: FastAPI, api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """Toilet paper is due since a week, both soaps since today, toothpaste only in a week.
    The last amount comes along only while its unit fits the base unit (REF-02)."""
    rows = {}
    for name, last_purchased_on in (
        ("Zahnpasta", date(2026, 9, 6)),
        ("Seife", date(2026, 8, 30)),
        ("Flüssigseife", date(2026, 8, 30)),
    ):
        ingredient = await create_ingredient(api, anna, name, base_unit="piece")
        rows[name] = await make_recurring(api, anna, ingredient["id"], 4, last_purchased_on)
    rows["Klopapier"] = await make_recurring(api, anna, toilet_paper["id"], 4, FIVE_WEEKS_AGO)
    await store_purchases(app, rows["Klopapier"]["id"], last_amount=12, last_unit="piece")
    await store_purchases(app, rows["Seife"]["id"], last_amount=200, last_unit="g")
    draft = await create_list(api, anna)

    assert [
        (item["ingredient"]["name"], item["due_on"], item["days_until_due"], item["last_amount"])
        for item in draft["due_items"]
    ] == [
        ("Klopapier", "2026-09-20", -7, {"value": 12, "unit": "piece"}),
        ("Flüssigseife", "2026-09-27", 0, None),
        ("Seife", "2026-09-27", 0, None),
    ]


async def test_an_ingredient_on_the_list_is_not_offered(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """Whether its line comes from a meal, from a linked extra item or is hidden (LIST-07)."""
    names = ("Spülmaschinentabs", "Zahnpasta", "Duschgel")
    tabs, toothpaste, shower_gel = [
        await create_ingredient(api, anna, name, base_unit="piece") for name in names
    ]
    for ingredient in (toilet_paper, tabs, toothpaste, shower_gel):
        await make_recurring(api, anna, ingredient["id"], 4, FIVE_WEEKS_AGO)
    draft = await create_list(api, anna)
    list_id = draft["id"]
    assert offered(draft) == ["Duschgel", "Klopapier", "Spülmaschinentabs", "Zahnpasta"]

    meal = await create_meal(
        api, anna, "Putztag", ingredients=[{"ingredient_id": tabs["id"], "amount": 2}]
    )
    await added(api, anna, list_id, meal["id"])
    await extra_added(api, anna, list_id, ingredient_id=toothpaste["id"])
    await extra_added(api, anna, list_id, ingredient_id=shower_gel["id"])
    hidden = await api.post(
        f"/api/lists/{list_id}/lines/i:{shower_gel['id']}/hide", headers=anna.headers
    )
    assert hidden.status_code == 200, hidden.text
    assert by_key(hidden.json(), f"i:{shower_gel['id']}")["hidden"] is True
    assert offered(hidden.json()) == ["Klopapier"]


async def test_only_drafts_one_can_edit_offer_due_items(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, toilet_paper: Any
) -> None:
    """Not while shopping, not on a done list (LIST-16), not read-only (LIST-05): carl sees
    anna's public draft and has a due item of his own; ben sees anna's unshared draft."""
    await make_couple(api, anna, ben)
    await set_privacy(api, anna, lists_public=True)
    await make_recurring(api, anna, toilet_paper["id"], 4, FIVE_WEEKS_AGO)
    await make_recurring(api, carl, toilet_paper["id"], 4, FIVE_WEEKS_AGO)
    draft = await create_list(api, anna)
    unshared = await api.patch(
        f"/api/lists/{draft['id']}", json={"shared_with_partner": False}, headers=anna.headers
    )
    assert offered(unshared.json()) == ["Klopapier"]
    assert offered(await detail(api, carl, draft["id"])) == []
    assert offered(await detail(api, ben, draft["id"])) == []

    shopping = await start_shopping(api, anna, draft["id"])
    assert offered(shopping) == []
    done = await applied(api, anna, draft["id"], op("list.finish", at=START))
    assert done["status"] == "done"
    assert offered(done) == []
    assert offered(await detail(api, anna, draft["id"])) == []


# --- hiding a due item on a list ------------------------------------------------------------


async def hide(api: AsyncClient, user: Account, list_id: str, ingredient_id: str) -> Any:
    return await api.post(
        f"/api/lists/{list_id}/due-items/{ingredient_id}/hide", headers=user.headers
    )


async def test_hiding_a_due_item_hides_it_on_that_list_for_everyone(
    api: AsyncClient, anna: Account, ben: Account, toilet_paper: Any
) -> None:
    """✕ in the "Fällig" box: gone on this draft, for ben too, and still offered on the next
    draft. The list gets a new version; hiding it again changes nothing."""
    await make_couple(api, anna, ben)
    soap = await create_ingredient(api, anna, "Seife", base_unit="piece")
    for ingredient in (toilet_paper, soap):
        await make_recurring(api, anna, ingredient["id"], 4, FIVE_WEEKS_AGO)
    draft = await create_list(api, anna)

    response = await hide(api, ben, draft["id"], toilet_paper["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert (offered(body), body["version"]) == (["Seife"], draft["version"] + 1)
    assert offered(await detail(api, anna, draft["id"])) == ["Seife"]
    again = await hide(api, anna, draft["id"], toilet_paper["id"])
    assert again.json() == await detail(api, anna, draft["id"])
    assert again.json()["version"] == body["version"]
    assert offered(await create_list(api, ben)) == ["Klopapier", "Seife"]


async def test_hiding_is_refused_where_nothing_is_offered(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, toilet_paper: Any
) -> None:
    """Outside a draft 409 `list.not_draft`; read-only viewers 403; a list one can't see and
    an unknown ingredient 404."""
    await set_privacy(api, anna, lists_public=True)
    await make_recurring(api, anna, toilet_paper["id"], 4, FIVE_WEEKS_AGO)
    draft = await create_list(api, anna)
    assert error(await hide(api, carl, draft["id"], toilet_paper["id"])) == "common.forbidden"
    await set_privacy(api, anna, lists_public=False)
    assert error(await hide(api, carl, draft["id"], toilet_paper["id"])) == "common.not_found"
    unknown = await hide(api, anna, draft["id"], str(uuid.uuid4()))
    assert (unknown.status_code, error(unknown)) == (404, "common.not_found")

    await start_shopping(api, anna, draft["id"])
    response = await hide(api, anna, draft["id"], toilet_paper["id"])
    assert (response.status_code, error(response)) == (409, "list.not_draft")


# --- ingredients merged and deleted (ING-05) ------------------------------------------------


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


async def test_a_merge_moves_hidden_due_items_to_the_surviving_ingredient(
    api: AsyncClient, anna: Account, admin: Account, toilet_paper: Any
) -> None:
    """anna's "WC-Papier" is recurring and hidden on two drafts, on one of them together with
    "Klopapier". After merging it into "Klopapier", her item is "Klopapier", hidden on both
    drafts (the two hides collapse into one) and offered on a third."""
    duplicate = await create_ingredient(api, anna, "WC-Papier", base_unit="piece")
    await make_recurring(api, anna, duplicate["id"], 4, FIVE_WEEKS_AGO)
    one, both, other = [await create_list(api, anna) for _ in range(3)]
    for draft in (one, both):
        assert (await hide(api, anna, draft["id"], duplicate["id"])).status_code == 200
    assert (await hide(api, anna, both["id"], toilet_paper["id"])).status_code == 200

    response = await api.post(
        f"/api/admin/ingredients/{duplicate['id']}/merge",
        json={"into_id": toilet_paper["id"]},
        headers=admin.headers,
    )
    assert response.status_code == 200, response.text

    assert offered(await detail(api, anna, one["id"])) == []
    assert offered(await detail(api, anna, both["id"])) == []
    assert offered(await detail(api, anna, other["id"])) == ["Klopapier"]


async def test_deleting_an_ingredient_removes_its_hidden_due_items(
    api: AsyncClient, anna: Account, admin: Account, toilet_paper: Any
) -> None:
    """Hidden due items are no references (ING-05): they never block the delete and go with
    the ingredient."""
    await make_recurring(api, anna, toilet_paper["id"], 4, FIVE_WEEKS_AGO)
    draft = await create_list(api, anna)
    assert (await hide(api, anna, draft["id"], toilet_paper["id"])).status_code == 200

    response = await api.delete(
        f"/api/admin/ingredients/{toilet_paper['id']}", headers=admin.headers
    )
    assert response.status_code == 204, response.text
    assert offered(await detail(api, anna, draft["id"])) == []


# --- the offline copy, ops and polling (SYNC-02, SYNC-08) -----------------------------------


async def test_the_offline_copy_and_the_ops_response_carry_due_items(
    api: AsyncClient, anna: Account, toilet_paper: Any
) -> None:
    """They are list details too: the local copy has the box of a stored draft (SYNC-02),
    and an op on a draft answers with it."""
    await make_recurring(api, anna, toilet_paper["id"], 4, FIVE_WEEKS_AGO)
    draft = await create_list(api, anna)

    response = await api.get("/api/lists/sync", headers=anna.headers)
    assert response.status_code == 200, response.text
    [stored] = response.json()["lists"]
    assert offered(stored) == ["Klopapier"]
    after_op = await applied(
        api, anna, draft["id"], op("extra.add", extra_id=str(uuid.uuid4()), text="Kerzen")
    )
    assert offered(after_op) == ["Klopapier"]
    assert after_op["due_items"] == stored["due_items"]


async def test_a_poll_after_midnight_shows_a_newly_due_item_within_a_minute(
    make_settings: SettingsFactory, client_for: ClientFactory, migrated_database: Path
) -> None:
    """Polls are answered from the list cache (PERF-02), which nothing invalidates at midnight;
    its age limit of a minute does (SYNC-08). In Kolkata (UTC+5:30) midnight is 18:30 UTC, not
    on the hour, so the photo URLs' hour, also part of the cache key, doesn't change with it."""
    settings = make_settings(time_zone="Asia/Kolkata")
    settings.data_dir.mkdir(parents=True)
    shutil.copyfile(migrated_database, settings.database_path)
    app = create_app(settings)
    clock = app.state.clock = FakeClock()
    app.state.list_cache = ListCache(clock=clock.monotonic)
    async with client_for(app) as api:
        anna = await make_user(app, api, "anna")
        toilet_paper = await create_ingredient(api, anna, "Klopapier", base_unit="piece")
        # Bought a week ago, every week: due on 28 September, Kolkata time.
        await make_recurring(api, anna, toilet_paper["id"], 1, date(2026, 9, 21))
        draft = await create_list(api, anna)
        clock.advance(hours=6, minutes=29, seconds=30)  # 23:59:30 in Kolkata
        await login(api, anna)
        assert offered(await detail(api, anna, draft["id"])) == []

        clock.advance(seconds=31)  # 00:00:01: the poll still gets the cached list
        assert offered(await detail(api, anna, draft["id"])) == []
        clock.advance(seconds=29)  # a minute after it was built
        [due] = (await detail(api, anna, draft["id"]))["due_items"]
        assert (due["due_on"], due["days_until_due"]) == ("2026-09-28", 0)
