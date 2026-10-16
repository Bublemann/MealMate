"""Notices (D-51): what an admin's deletion of an ingredient leaves for the users who kept it as
a recurring item (ING-05), until each of them dismisses theirs.

The fake clock starts at 2026-09-27 12:00 UTC.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from tests.accounts import Account, FakeClock, error, make_couple, make_user
from tests.catalog import create_ingredient
from tests.recurring import make_recurring, notices, recurring


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


async def delete_ingredient(api: AsyncClient, admin: Account, ingredient_id: str) -> None:
    response = await api.delete(f"/api/admin/ingredients/{ingredient_id}", headers=admin.headers)
    assert response.status_code == 204, response.text


async def dismiss(api: AsyncClient, user: Account, notice_id: str) -> Response:
    return await api.post(f"/api/me/notices/{notice_id}/dismiss", headers=user.headers)


def kinds_and_params(body: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(notice["kind"], notice["params"]) for notice in body["notices"]]


async def test_a_new_user_has_no_notices(api: AsyncClient, anna: Account) -> None:
    assert await notices(api, anna) == {"notices": [], "count": 0}


# --- an ingredient kept as recurring is deleted (ING-05) -----------------------------------


async def test_deleting_a_recurring_ingredient_leaves_a_notice(
    api: AsyncClient, anna: Account, admin: Account, toilet_paper: Any, clock: FakeClock
) -> None:
    """A recurring item is no reference: the ingredient's usage stays at none, and the admin
    deletes it. The item goes, and anna learns of it with the name and brand it had."""
    await make_recurring(api, anna, toilet_paper["id"])
    url = f"/api/ingredients/{toilet_paper['id']}"
    usage = (await api.get(url, headers=anna.headers)).json()["usage"]
    assert usage == {"meals": 0, "lists": 0}
    clock.advance(minutes=5)

    await delete_ingredient(api, admin, toilet_paper["id"])

    assert await recurring(api, anna) == {"items": [], "due_count": 0}
    body = await notices(api, anna)
    assert body == {
        "notices": [
            {
                "id": body["notices"][0]["id"],
                "kind": "recurring_item.ingredient_deleted",
                "params": {"name": "Klopapier", "brand": None},
                "created_at": "2026-09-27T12:05:00Z",
            }
        ],
        "count": 1,
    }


async def test_both_partners_get_a_notice_and_no_one_else(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, admin: Account
) -> None:
    """The couple's set had it, so anna and ben get one notice each; carl, who keeps only
    another ingredient, gets none."""
    toilet_paper = await create_ingredient(api, anna, "Klopapier", brand="Zewa")
    toothpaste = await create_ingredient(api, carl, "Zahnpasta")
    await make_couple(api, anna, ben)
    await make_recurring(api, ben, toilet_paper["id"])
    await make_recurring(api, carl, toothpaste["id"])

    await delete_ingredient(api, admin, toilet_paper["id"])

    expected = [("recurring_item.ingredient_deleted", {"name": "Klopapier", "brand": "Zewa"})]
    assert kinds_and_params(await notices(api, anna)) == expected
    assert kinds_and_params(await notices(api, ben)) == expected
    assert await notices(api, carl) == {"notices": [], "count": 0}
    assert len((await recurring(api, carl))["items"]) == 1


async def test_unread_notices_come_newest_first(
    api: AsyncClient, anna: Account, admin: Account, toilet_paper: Any, clock: FakeClock
) -> None:
    toothpaste = await create_ingredient(api, anna, "Zahnpasta")
    await make_recurring(api, anna, toothpaste["id"])
    await make_recurring(api, anna, toilet_paper["id"])
    await delete_ingredient(api, admin, toothpaste["id"])
    clock.advance(minutes=10)
    await delete_ingredient(api, admin, toilet_paper["id"])

    body = await notices(api, anna)

    assert body["count"] == 2
    assert [(n["params"]["name"], n["created_at"]) for n in body["notices"]] == [
        ("Klopapier", "2026-09-27T12:10:00Z"),
        ("Zahnpasta", "2026-09-27T12:00:00Z"),
    ]


# --- dismiss --------------------------------------------------------------------------------


async def test_each_partner_dismisses_their_own_notice(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, admin: Account, toilet_paper: Any
) -> None:
    """anna's dismissal leaves ben's notice unread; dismissing again changes nothing, and
    carl can't dismiss anna's notice (SEC-04)."""
    await make_couple(api, anna, ben)
    await make_recurring(api, anna, toilet_paper["id"])
    await delete_ingredient(api, admin, toilet_paper["id"])
    [notice] = (await notices(api, anna))["notices"]
    unread_of_ben = await notices(api, ben)

    for user, notice_id in (
        (carl, notice["id"]),
        (anna, unread_of_ben["notices"][0]["id"]),
        (anna, "0190c0de-0000-7000-8000-000000000000"),
    ):
        response = await dismiss(api, user, notice_id)
        assert (response.status_code, error(response)) == (404, "common.not_found")
    assert (await notices(api, anna))["count"] == 1

    assert (await dismiss(api, anna, notice["id"])).status_code == 204
    assert await notices(api, anna) == {"notices": [], "count": 0}
    assert await notices(api, ben) == unread_of_ben
    assert (await dismiss(api, anna, notice["id"])).status_code == 204
    assert await notices(api, anna) == {"notices": [], "count": 0}
