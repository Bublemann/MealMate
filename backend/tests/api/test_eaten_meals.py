"""Eaten meals on done lists (SHOP-07, D-55): anyone who may edit a done list marks its meals
eaten and clears that again; nothing else on it changes, and drafts and lists being shopped
refuse it."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from tests.accounts import Account, FakeClock, error, login, make_couple, make_user, set_privacy
from tests.catalog import category_ids, create_item
from tests.lists import added, applied, create_list, detail, op, start_shopping
from tests.meals import create_meal


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
async def meals(api: AsyncClient, anna: Account) -> list[Any]:
    categories = await category_ids(api, anna)
    flour = await create_item(api, anna, "Mehl", category_id=categories["baking"])
    return [
        await create_meal(
            api, anna, name, ingredients=[{"item_id": flour["id"], "amount": 100, "unit": "g"}]
        )
        for name in ("Brot", "Pizza")
    ]


async def list_with(api: AsyncClient, user: Account, meals: list[Any]) -> Any:
    shopping_list = await create_list(api, user, "Woche")
    for meal in meals:
        body = await added(api, user, shopping_list["id"], meal["id"])
    return body


async def done_list(api: AsyncClient, user: Account, meals: list[Any]) -> Any:
    shopping_list = await list_with(api, user, meals)
    await start_shopping(api, user, shopping_list["id"])
    return await applied(api, user, shopping_list["id"], op("list.finish"))


def set_eaten(
    api: AsyncClient, user: Account, list_id: str, list_meal_id: str, *, eaten: bool
) -> Any:
    return api.put(
        f"/api/lists/{list_id}/meals/{list_meal_id}/eaten",
        json={"eaten": eaten},
        headers=user.headers,
    )


def eaten(list_detail: Any) -> list[tuple[str, bool]]:
    return [(entry["name"], entry["eaten"]) for entry in list_detail["meals"]]


async def test_marking_meals_eaten(
    api: AsyncClient, anna: Account, clock: FakeClock, meals: list[Any]
) -> None:
    done = await done_list(api, anna, meals)
    list_id, brot = done["id"], done["meals"][0]["id"]
    assert eaten(done) == [("Brot", False), ("Pizza", False)]
    clock.advance(minutes=5)
    await login(api, anna)

    response: Response = await set_eaten(api, anna, list_id, brot, eaten=True)

    assert response.status_code == 200, response.text
    body = response.json()
    assert eaten(body) == [("Brot", True), ("Pizza", False)]
    assert (body["status"], body["version"]) == ("done", done["version"] + 1)
    assert body["updated_at"] == "2026-09-27T12:05:00Z"
    assert body["lines"] == done["lines"]
    assert eaten(await detail(api, anna, list_id)) == [("Brot", True), ("Pizza", False)]
    # Again changes nothing.
    response = await set_eaten(api, anna, list_id, brot, eaten=True)
    assert response.status_code == 200
    again = response.json()
    assert (eaten(again), again["version"]) == (eaten(body), body["version"])

    response = await set_eaten(api, anna, list_id, brot, eaten=False)

    assert response.status_code == 200
    assert eaten(response.json()) == [("Brot", False), ("Pizza", False)]


async def test_who_may_mark_meals_eaten(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, meals: list[Any]
) -> None:
    await make_couple(api, anna, ben)
    shared = await done_list(api, anna, meals)
    unshared = await create_list(api, anna, "Privat")
    await api.patch(
        f"/api/lists/{unshared['id']}", json={"shared_with_partner": False}, headers=anna.headers
    )
    await added(api, anna, unshared["id"], meals[0]["id"])
    await start_shopping(api, anna, unshared["id"])
    unshared = await applied(api, anna, unshared["id"], op("list.finish"))

    # The partner edits the shared list ...
    response = await set_eaten(api, ben, shared["id"], shared["meals"][1]["id"], eaten=True)
    assert response.status_code == 200, response.text
    assert eaten(response.json()) == [("Brot", False), ("Pizza", True)]
    # ... but only sees the unshared one; carl sees anna's public lists read-only.
    for user, target in ((ben, unshared), (carl, shared)):
        response = await set_eaten(api, user, target["id"], target["meals"][0]["id"], eaten=True)
        assert (response.status_code, error(response)) == (403, "common.forbidden")
    assert eaten(await detail(api, anna, unshared["id"])) == [("Brot", False)]


async def test_only_done_lists_have_eaten_meals(
    api: AsyncClient, anna: Account, meals: list[Any]
) -> None:
    draft = await list_with(api, anna, meals)
    shopping = await list_with(api, anna, meals[:1])
    shopping = await start_shopping(api, anna, shopping["id"])

    for target in (draft, shopping):
        response = await set_eaten(api, anna, target["id"], target["meals"][0]["id"], eaten=True)
        assert (response.status_code, error(response)) == (409, "list.not_done")
    assert eaten(await detail(api, anna, draft["id"])) == [("Brot", False), ("Pizza", False)]

    done = await done_list(api, anna, meals[:1])
    response = await set_eaten(api, anna, done["id"], draft["meals"][0]["id"], eaten=True)
    assert (response.status_code, error(response)) == (404, "common.not_found")


async def test_eaten_stays_when_a_list_is_reopened(
    api: AsyncClient, anna: Account, meals: list[Any]
) -> None:
    done = await done_list(api, anna, meals)
    await set_eaten(api, anna, done["id"], done["meals"][0]["id"], eaten=True)

    reopened = await api.post(f"/api/lists/{done['id']}/reopen", headers=anna.headers)

    assert reopened.status_code == 200, reopened.text
    assert eaten(reopened.json()) == [("Brot", True), ("Pizza", False)]
    # Shopping again copies the meals as they are, not eaten.
    again = await api.post(f"/api/lists/{done['id']}/shop-again", headers=anna.headers)
    assert again.status_code == 409
    await applied(api, anna, done["id"], op("list.finish"))
    again = await api.post(f"/api/lists/{done['id']}/shop-again", headers=anna.headers)
    assert eaten(again.json()["list"]) == [("Brot", False), ("Pizza", False)]


async def test_private_and_detached_meals_can_be_eaten(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, meals: list[Any]
) -> None:
    """Whoever edits the list ticks every meal on it, also one they can't see the details of
    (VIS-06) and one that is no longer available (LIST-15)."""
    await make_couple(api, anna, ben)
    curry = await create_meal(api, carl, "Curry", ingredients=[])
    done = await list_with(api, anna, [meals[0], curry])
    await api.delete(f"/api/meals/{meals[0]['id']}", headers=anna.headers)
    await start_shopping(api, anna, done["id"])
    # Frozen, carl's meal stays on the list when he makes his meals private.
    await set_privacy(api, carl, meals_public=False)
    done = await applied(api, anna, done["id"], op("list.finish"))
    detached, private = done["meals"]
    assert (detached["detached"], private["private"]) == ("deleted", True)

    for entry in (detached, private):
        response = await set_eaten(api, ben, done["id"], entry["id"], eaten=True)
        assert response.status_code == 200, response.text
    assert [entry["eaten"] for entry in (await detail(api, anna, done["id"]))["meals"]] == [
        True,
        True,
    ]
