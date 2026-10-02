"""Shopping lists: create, read, rename, share, delete, meals, extra items, hidden lines, copy,
"recently used" meals, access rules and ETags (LIST-01..10, LIST-13, CPL-02..04, VIS-02/03/06,
UI-02, MEAL-09)."""

import hashlib
import uuid
from base64 import urlsafe_b64encode
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Connection, event, select

from app.db.session import Database
from app.models import ListExtraItem, ListLineState, ListMeal, ShoppingList
from app.services.list_cache import ListCache
from tests.accounts import (
    Account,
    FakeClock,
    error,
    fields,
    login,
    make_couple,
    make_user,
    scalars,
    set_privacy,
)
from tests.catalog import category_ids, create_ingredient, ref
from tests.lists import (
    add_extra,
    add_meal,
    added,
    applied,
    create_list,
    detail,
    extra_added,
    feed_page,
    get_list,
    line,
    op,
    set_status,
    start_shopping,
    summaries,
)
from tests.meals import create_meal, jpeg, upload


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
async def dora(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "dora")


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


@pytest.fixture
async def flour(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Mehl")


@pytest.fixture
async def salt(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Salz")


async def patch(api: AsyncClient, user: Account, list_id: str, **body: Any) -> Any:
    return await api.patch(f"/api/lists/{list_id}", json=body, headers=user.headers)


async def patch_extra(
    api: AsyncClient, user: Account, list_id: str, extra_id: str, **body: Any
) -> Any:
    return await api.patch(
        f"/api/lists/{list_id}/extra-items/{extra_id}", json=body, headers=user.headers
    )


async def hide(
    api: AsyncClient, user: Account, list_id: str, key: str, action: str = "hide"
) -> Any:
    return await api.post(f"/api/lists/{list_id}/lines/{key}/{action}", headers=user.headers)


def names(items: list[Any]) -> list[str | None]:
    return [item["name"] for item in items]


# --- create and read (LIST-01, LIST-02, LIST-14) --------------------------------------------


async def test_create_an_empty_draft(api: AsyncClient, anna: Account) -> None:
    response = await api.post("/api/lists", json={}, headers=anna.headers)

    assert response.status_code == 201
    body = response.json()
    assert 0 <= body["reminder_seed"] <= 9999
    assert body == {
        "id": body["id"],
        "name": None,
        "status": "draft",
        "version": 0,
        "created_at": "2026-09-27T12:00:00Z",
        "updated_at": "2026-09-27T12:00:00Z",
        "shopping_started_at": None,
        "finished_at": None,
        "owner": ref(anna),
        "is_owner": True,
        "can_edit": True,
        "shared_with_partner": False,
        "reminder_seed": body["reminder_seed"],
        "meals": [],
        "lines": [],
        "extra_items": [],
    }
    assert await detail(api, anna, body["id"]) == body


async def test_names(api: AsyncClient, anna: Account) -> None:
    assert (await create_list(api, anna, "  Grillabend "))["name"] == "Grillabend"
    assert (await create_list(api, anna, "   "))["name"] is None
    assert (await api.post("/api/lists", headers=anna.headers)).status_code == 422


@pytest.mark.parametrize(
    ("body", "problems"),
    [
        ({"name": "x" * 61}, {("body", "name"): "too_long"}),
        ({"name": "Bell\x07"}, {("body", "name"): "invalid_format"}),
        ({"name": 5}, {("body", "name"): "invalid"}),
    ],
)
async def test_create_validation(
    api: AsyncClient, anna: Account, body: dict[str, Any], problems: dict[Any, str]
) -> None:
    response = await api.post("/api/lists", json=body, headers=anna.headers)
    assert response.status_code == 422
    assert fields(response) == problems


async def test_new_lists_are_shared_while_in_a_couple(
    api: AsyncClient, anna: Account, ben: Account
) -> None:
    """CPL-02: the switch defaults to on for new lists while the owner is in a couple."""
    assert (await create_list(api, anna))["shared_with_partner"] is False
    await make_couple(api, anna, ben)
    assert (await create_list(api, anna))["shared_with_partner"] is True
    assert (await create_list(api, ben))["shared_with_partner"] is True


async def test_unknown_list(api: AsyncClient, anna: Account) -> None:
    for method in ("GET", "PATCH", "DELETE"):
        response = await api.request(method, "/api/lists/nope", json={}, headers=anna.headers)
        assert response.status_code == 404, method
        assert error(response) == "common.not_found"


async def test_list_routes_need_a_token(api: AsyncClient) -> None:
    for method, path in (
        ("GET", "/api/lists"),
        ("POST", "/api/lists"),
        ("GET", "/api/lists/x"),
        ("PATCH", "/api/lists/x"),
        ("DELETE", "/api/lists/x"),
        ("POST", "/api/lists/x/copy"),
        ("POST", "/api/lists/x/meals"),
        ("PATCH", "/api/lists/x/meals/y"),
        ("DELETE", "/api/lists/x/meals/y"),
        ("POST", "/api/lists/x/extra-items"),
        ("PATCH", "/api/lists/x/extra-items/y"),
        ("DELETE", "/api/lists/x/extra-items/y"),
        ("POST", f"/api/lists/x/lines/i:{uuid.uuid4()}/hide"),
        ("POST", f"/api/lists/x/lines/i:{uuid.uuid4()}/unhide"),
        ("GET", "/api/meals/recent"),
    ):
        response = await api.request(method, path)
        assert response.status_code == 401, (method, path)
        assert error(response) == "common.unauthorized"


# --- rename, share switch, delete (LIST-02, CPL-02, LIST-13) --------------------------------


async def test_rename(api: AsyncClient, anna: Account, clock: FakeClock) -> None:
    created = await create_list(api, anna)
    clock.advance(minutes=5)

    renamed = await patch(api, anna, created["id"], name=" Grillabend ")

    assert renamed.status_code == 200
    body = renamed.json()
    assert body["name"] == "Grillabend"
    assert body["version"] == 1
    assert body["updated_at"] == "2026-09-27T12:05:00Z"
    assert body["created_at"] == created["created_at"]
    # Nothing changed: no new version.
    clock.advance(minutes=5)
    same = (await patch(api, anna, created["id"], name="Grillabend")).json()
    assert (same["version"], same["updated_at"]) == (1, "2026-09-27T12:05:00Z")
    assert (await patch(api, anna, created["id"])).json()["version"] == 1
    # Null or empty goes back to the default name.
    assert (await patch(api, anna, created["id"], name=None)).json()["name"] is None
    assert (await patch(api, anna, created["id"], name="x")).json()["version"] == 3
    assert (await patch(api, anna, created["id"], name="")).json()["name"] is None


async def test_share_switch(api: AsyncClient, anna: Account, ben: Account) -> None:
    alone = await create_list(api, anna)
    response = await patch(api, anna, alone["id"], shared_with_partner=True)
    assert response.status_code == 422
    assert fields(response) == {("body", "shared_with_partner"): "invalid"}
    assert (await patch(api, anna, alone["id"], shared_with_partner=False)).status_code == 200

    await make_couple(api, anna, ben)
    on = await patch(api, anna, alone["id"], shared_with_partner=True)
    assert on.json()["shared_with_partner"] is True
    assert on.json()["version"] == 1
    off = await patch(api, anna, alone["id"], shared_with_partner=False, name="Party")
    assert (off.json()["shared_with_partner"], off.json()["name"]) == (False, "Party")
    assert off.json()["version"] == 2

    response = await patch(api, anna, alone["id"], shared_with_partner=None)
    assert response.status_code == 422
    assert fields(response) == {("body", "shared_with_partner"): "invalid"}


async def test_delete(app: FastAPI, api: AsyncClient, anna: Account, flour: Any) -> None:
    meal = await create_meal(api, anna, "Brot", ingredients=[{"ingredient_id": flour["id"]}])
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal["id"])
    await extra_added(api, anna, shopping_list["id"], text="Kerzen")
    await hide(api, anna, shopping_list["id"], f"i:{flour['id']}")

    response = await api.delete(f"/api/lists/{shopping_list['id']}", headers=anna.headers)

    assert response.status_code == 204
    assert (await get_list(api, anna, shopping_list["id"])).status_code == 404
    for model in (ShoppingList, ListMeal, ListExtraItem, ListLineState):
        assert await scalars(app, select(model)) == [], model
    again = await api.delete(f"/api/lists/{shopping_list['id']}", headers=anna.headers)
    assert again.status_code == 404


# --- who may do what (plan § 5.5, CPL-02..04, CPL-07, VIS-02/03) ---------------------------


async def probe(api: AsyncClient, user: Account, list_id: str) -> dict[str, int]:
    """The status of each kind of request `user` makes on the list; deleting comes last."""
    viewed = await get_list(api, user, list_id)
    results = {
        "view": viewed.status_code,
        "rename": (await patch(api, user, list_id, name="Neu")).status_code,
        "share": (await patch(api, user, list_id, shared_with_partner=False)).status_code,
        "extra": (await add_extra(api, user, list_id, text="Kerzen")).status_code,
        "hide": (await hide(api, user, list_id, f"x:{uuid.uuid4()}")).status_code,
        "copy": (await api.post(f"/api/lists/{list_id}/copy", headers=user.headers)).status_code,
        "delete": (await api.delete(f"/api/lists/{list_id}", headers=user.headers)).status_code,
    }
    if viewed.status_code == 200:
        results["is_owner"] = viewed.json()["is_owner"]
        results["can_edit"] = viewed.json()["can_edit"]
    return results


OWNER = {
    "view": 200,
    "rename": 200,
    "share": 200,
    "extra": 201,
    "hide": 200,
    "copy": 201,
    "delete": 204,
    "is_owner": True,
    "can_edit": True,
}
EDITOR = OWNER | {"share": 403, "delete": 403, "is_owner": False}
READER = EDITOR | {"rename": 403, "extra": 403, "hide": 403, "can_edit": False}
NOBODY = {key: 404 for key in ("view", "rename", "share", "extra", "hide", "copy", "delete")}


async def test_owner(api: AsyncClient, anna: Account) -> None:
    assert await probe(api, anna, (await create_list(api, anna))["id"]) == OWNER


async def test_partner_edits_shared_lists(api: AsyncClient, anna: Account, ben: Account) -> None:
    await make_couple(api, anna, ben)
    await set_privacy(api, anna, lists_public=False)
    assert await probe(api, ben, (await create_list(api, anna))["id"]) == EDITOR


async def test_partner_reads_unshared_lists(api: AsyncClient, anna: Account, ben: Account) -> None:
    """CPL-02/04: the partner sees unshared lists read-only, even when they are private."""
    await make_couple(api, anna, ben)
    await set_privacy(api, anna, lists_public=False)
    shopping_list = await create_list(api, anna)
    await patch(api, anna, shopping_list["id"], shared_with_partner=False)
    assert await probe(api, ben, shopping_list["id"]) == READER


async def test_others_read_public_lists(api: AsyncClient, anna: Account, carl: Account) -> None:
    assert await probe(api, carl, (await create_list(api, anna))["id"]) == READER


async def test_private_lists_are_hidden_from_others(
    api: AsyncClient, anna: Account, carl: Account
) -> None:
    await set_privacy(api, anna, lists_public=False)
    assert await probe(api, carl, (await create_list(api, anna))["id"]) == NOBODY


async def test_after_the_couple_ended(api: AsyncClient, anna: Account, ben: Account) -> None:
    """CPL-05: the list stays with its creator; the ex-partner sees it only if it is public."""
    await make_couple(api, anna, ben)
    public = await create_list(api, anna)
    assert (await api.delete("/api/couple", headers=ben.headers)).status_code == 204
    assert (await detail(api, anna, public["id"]))["shared_with_partner"] is False
    assert await probe(api, ben, public["id"]) == READER

    await set_privacy(api, anna, lists_public=False)
    assert await probe(api, ben, (await create_list(api, anna))["id"]) == NOBODY


async def test_deactivated_partner_keeps_the_shared_lists(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, admin: Account
) -> None:
    """CPL-07: the couple and the shared lists stay while a partner is deactivated."""
    await make_couple(api, anna, ben)
    await set_privacy(api, ben, lists_public=False)
    shopping_list = await create_list(api, ben)
    response = await api.patch(
        f"/api/admin/users/{ben.id}", json={"is_active": False}, headers=admin.headers
    )
    assert response.status_code == 200

    body = await detail(api, anna, shopping_list["id"])
    assert body["owner"] == ref(ben) | {"deactivated": True}
    assert await probe(api, anna, shopping_list["id"]) == EDITOR


# --- the Lists feed (UI-02) -----------------------------------------------------------------


async def test_the_feed_shows_every_list_one_can_see_in_every_state(
    api: AsyncClient,
    anna: Account,
    ben: Account,
    carl: Account,
    dora: Account,
    clock: FakeClock,
    flour: Any,
) -> None:
    await make_couple(api, anna, ben)
    await set_privacy(api, dora, lists_public=False)
    await set_privacy(api, ben, lists_public=False)
    own = await create_list(api, anna, "Anna")
    clock.advance(minutes=1)
    await create_list(api, ben, "Ben geteilt")
    clock.advance(minutes=1)
    unshared = await create_list(api, ben, "Ben privat")
    await patch(api, ben, unshared["id"], shared_with_partner=False)
    await start_shopping(api, ben, unshared["id"])
    clock.advance(minutes=1)
    carls = await create_list(api, carl, "Carl")
    await start_shopping(api, carl, carls["id"])
    await applied(api, carl, carls["id"], op("list.finish", at=clock.now))
    clock.advance(minutes=1)
    await create_list(api, dora, "Dora")
    meal = await create_meal(api, anna, "Brot", ingredients=[{"ingredient_id": flour["id"]}])
    await added(api, anna, own["id"], meal["id"])
    await extra_added(api, anna, own["id"], text="Kerzen")
    await extra_added(api, anna, own["id"], text="Servietten")
    await hide(api, anna, own["id"], f"i:{flour['id']}")

    feed = await summaries(api, anna)
    # Newest created first; Dora's lists are private, Carl's done list is public.
    assert names(feed) == ["Carl", "Ben privat", "Ben geteilt", "Anna"]
    assert [
        (item["status"], item["is_owner"], item["can_edit"], item["shared_with_partner"])
        for item in feed
    ] == [
        ("done", False, False, False),
        ("shopping", False, False, False),
        ("draft", False, True, True),
        ("draft", True, True, True),
    ]
    assert feed[0]["finished_at"] == "2026-09-27T12:03:00Z"
    assert feed[3] == {
        "id": own["id"],
        "name": "Anna",
        "status": "draft",
        "created_at": "2026-09-27T12:00:00Z",
        "updated_at": "2026-09-27T12:04:00Z",
        "finished_at": None,
        "owner": ref(anna),
        "is_owner": True,
        "can_edit": True,
        "shared_with_partner": True,
        "meal_count": 1,
        "line_count": 2,  # the flour line is hidden
    }
    assert names(await summaries(api, ben)) == ["Carl", "Ben privat", "Ben geteilt", "Anna"]
    assert names(await summaries(api, carl)) == ["Carl", "Anna"]
    assert names(await summaries(api, dora)) == ["Dora", "Carl", "Anna"]


async def test_a_list_keeps_its_place_in_the_feed(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    await make_couple(api, anna, ben)
    first = await create_list(api, anna, "Erste")
    clock.advance(minutes=1)
    second = await create_list(api, ben, "Zweite")
    # Created at the same time: the higher id comes first.
    third = await create_list(api, anna, "Dritte")
    order = [third["id"], second["id"], first["id"]]
    assert [item["id"] for item in await summaries(api, anna)] == order

    clock.advance(minutes=1)
    assert (await patch(api, anna, first["id"], name="Erste!")).status_code == 200
    await extra_added(api, ben, first["id"], text="Kerzen")
    assert [item["id"] for item in await summaries(api, anna)] == order
    await start_shopping(api, anna, first["id"])
    assert [item["id"] for item in await summaries(api, anna)] == order
    await applied(api, ben, first["id"], op("list.finish", at=clock.now))
    feed = await summaries(api, ben)
    assert [(item["id"], item["status"]) for item in feed] == [
        (third["id"], "draft"),
        (second["id"], "draft"),
        (first["id"], "done"),
    ]


async def test_the_feed_comes_in_pages_of_30(
    api: AsyncClient, anna: Account, clock: FakeClock
) -> None:
    created = []
    for index in range(32):
        # Two lists per second: the first page ends between two lists created together.
        if index % 2 == 1:
            clock.advance(seconds=1)
        created.append((await create_list(api, anna, f"Liste {index}"))["id"])
    newest_first = created[::-1]

    first = await feed_page(api, anna)
    assert [item["id"] for item in first["lists"]] == newest_first[:30]
    assert first["next_cursor"] is not None
    # A list created meanwhile shows on the first page, not on the next.
    await create_list(api, anna, "Neu")
    second = await feed_page(api, anna, first["next_cursor"])
    assert [item["id"] for item in second["lists"]] == newest_first[30:]
    assert second["next_cursor"] is None

    # Not base64, empty, a time without an id, a time without a zone, an empty id, too long.
    made_up = [
        urlsafe_b64encode(raw.encode()).decode()
        for raw in ("2026-09-27", "2026-09-27T12:00:00 x", "2026-09-27T12:00:00+00:00 ")
    ]
    for cursor in ["kaputt!", "", *made_up, "x" * 200]:
        response = await api.get("/api/lists", params={"cursor": cursor}, headers=anna.headers)
        assert response.status_code == 422, cursor
        assert set(fields(response)) == {("query", "cursor")}


# --- meals on a list (LIST-03, LIST-04, VIS-06) ---------------------------------------------


async def test_add_meals(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock, flour: Any
) -> None:
    pancakes = await create_meal(
        api, anna, "Pfannkuchen", servings=2, ingredients=[{"ingredient_id": flour["id"]}]
    )
    photo = await upload(api, anna, pancakes["id"], jpeg())
    assert photo.status_code == 200
    salad = await create_meal(api, ben, "Salat", servings=3)
    shopping_list = await create_list(api, anna)
    clock.advance(minutes=1)

    first = await added(api, anna, shopping_list["id"], pancakes["id"])
    body = await added(api, anna, shopping_list["id"], salad["id"], servings=5)

    assert first["version"] == 1
    assert body["version"] == 2
    assert body["updated_at"] == "2026-09-27T12:01:00Z"
    [entry, other] = body["meals"]
    assert entry == {
        "id": entry["id"],
        "meal_id": pancakes["id"],
        "name": "Pfannkuchen",
        "private": False,
        "owner": ref(anna),
        "thumb_url": entry["thumb_url"],
        "servings": 2,
        "meal_servings": 2,
        "detached": None,
    }
    # The same thumbnail as the meal's; the signature depends on the time.
    thumb = photo.json()["photo"]["thumb_url"]
    assert entry["thumb_url"].split("?")[0] == thumb.split("?")[0]
    assert (other["name"], other["owner"], other["thumb_url"]) == ("Salat", ref(ben), None)
    assert (other["servings"], other["meal_servings"]) == (5, 3)


async def test_adding_a_meal_again_raises_its_servings(
    api: AsyncClient, anna: Account, flour: Any
) -> None:
    """LIST-04: a meal appears at most once per list."""
    meal = await create_meal(api, anna, "Brot", servings=4)
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal["id"], servings=2)

    body = await added(api, anna, shopping_list["id"], meal["id"])
    assert [entry["servings"] for entry in body["meals"]] == [6]
    body = await added(api, anna, shopping_list["id"], meal["id"], servings=3)
    assert [entry["servings"] for entry in body["meals"]] == [9]
    body = await added(api, anna, shopping_list["id"], meal["id"], servings=99)
    assert [entry["servings"] for entry in body["meals"]] == [99]  # capped
    assert body["version"] == 4


async def test_adding_needs_a_visible_meal(
    api: AsyncClient, anna: Account, ben: Account, carl: Account
) -> None:
    await set_privacy(api, carl, meals_public=False)
    hidden = await create_meal(api, carl, "Geheim")
    await make_couple(api, anna, ben)
    await set_privacy(api, ben, meals_public=False)
    partners = await create_meal(api, ben, "Bens")
    shopping_list = await create_list(api, anna)

    for meal_id in (hidden["id"], "unknown"):
        response = await add_meal(api, anna, shopping_list["id"], meal_id)
        assert response.status_code == 422
        assert fields(response) == {("body", "meal_id"): "invalid"}
    assert (await add_meal(api, anna, shopping_list["id"], partners["id"])).status_code == 200


@pytest.mark.parametrize(
    ("body", "problems"),
    [
        ({}, {("body", "meal_id"): "required"}),
        ({"meal_id": ""}, {("body", "meal_id"): "too_short"}),
        ({"meal_id": "m", "servings": 0}, {("body", "servings"): "out_of_range"}),
        ({"meal_id": "m", "servings": 100}, {("body", "servings"): "out_of_range"}),
    ],
)
async def test_add_meal_validation(
    api: AsyncClient, anna: Account, body: dict[str, Any], problems: dict[Any, str]
) -> None:
    shopping_list = await create_list(api, anna)
    response = await api.post(
        f"/api/lists/{shopping_list['id']}/meals", json=body, headers=anna.headers
    )
    assert response.status_code == 422
    assert fields(response) == problems


async def test_change_servings_and_remove(api: AsyncClient, anna: Account, carl: Account) -> None:
    meal = await create_meal(api, anna, "Brot", servings=2)
    shopping_list = await create_list(api, anna)
    other = await create_list(api, carl)
    [entry] = (await added(api, anna, shopping_list["id"], meal["id"]))["meals"]
    url = f"/api/lists/{shopping_list['id']}/meals/{entry['id']}"

    response = await api.patch(url, json={"servings": 7}, headers=anna.headers)
    assert response.status_code == 200
    assert (response.json()["meals"][0]["servings"], response.json()["version"]) == (7, 2)
    same = await api.patch(url, json={"servings": 7}, headers=anna.headers)
    assert same.json()["version"] == 2
    for servings, code in ((0, "out_of_range"), (100, "out_of_range"), (None, "invalid")):
        response = await api.patch(url, json={"servings": servings}, headers=anna.headers)
        assert fields(response) == {("body", "servings"): code}
    wrong_list = f"/api/lists/{other['id']}/meals/{entry['id']}"
    response = await api.patch(wrong_list, json={"servings": 3}, headers=carl.headers)
    assert response.status_code == 404
    assert (await api.delete(wrong_list, headers=carl.headers)).status_code == 404

    removed = await api.delete(url, headers=anna.headers)
    assert removed.status_code == 200
    assert (removed.json()["meals"], removed.json()["version"]) == ([], 3)
    assert (await api.delete(url, headers=anna.headers)).status_code == 404
    response = await api.patch(url, json={"servings": 3}, headers=anna.headers)
    assert response.status_code == 404


async def test_private_meals_on_a_visible_list(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, flour: Any
) -> None:
    """VIS-06: a meal the viewer cannot see shows only its servings, in the meals and the
    line sources; the lines themselves are shown."""
    await make_couple(api, carl, ben)
    await set_privacy(api, carl, meals_public=False)
    secret = await create_meal(
        api,
        carl,
        "Geheimrezept",
        servings=2,
        ingredients=[{"ingredient_id": flour["id"], "amount": 100, "unit": "g"}],
    )
    await upload(api, carl, secret["id"], jpeg())
    public = await create_meal(
        api, anna, "Brot", ingredients=[{"ingredient_id": flour["id"], "amount": 50, "unit": "g"}]
    )
    shopping_list = await create_list(api, carl, "Grillabend")
    await added(api, carl, shopping_list["id"], secret["id"], servings=4)
    await added(api, carl, shopping_list["id"], public["id"])

    seen = await detail(api, anna, shopping_list["id"])
    [private, visible] = seen["meals"]
    assert private == {
        "id": private["id"],
        "meal_id": None,
        "name": None,
        "private": True,
        "owner": None,
        "thumb_url": None,
        "servings": 4,
        "meal_servings": 2,
        "detached": None,
    }
    assert (visible["name"], visible["private"]) == ("Brot", False)
    [flour_line] = seen["lines"]
    assert flour_line["amounts"] == [{"value": 250, "unit": "g"}]
    assert [(s["meal_name"], s["private"], s["servings"]) for s in flour_line["sources"]] == [
        (None, True, 4),
        ("Brot", False, 1),
    ]
    # The owner and their partner see everything.
    for viewer in (carl, ben):
        body = await detail(api, viewer, shopping_list["id"])
        assert [entry["name"] for entry in body["meals"]] == ["Geheimrezept", "Brot"]
        assert body["meals"][0]["thumb_url"] is not None
        assert [s["private"] for s in body["lines"][0]["sources"]] == [False, False]


# --- extra items (LIST-06) ------------------------------------------------------------------


async def test_linked_and_free_text_items(
    api: AsyncClient, anna: Account, ben: Account, flour: Any, clock: FakeClock
) -> None:
    categories = await category_ids(api, anna)
    shopping_list = await create_list(api, anna)
    clock.advance(minutes=1)

    body = await extra_added(
        api, anna, shopping_list["id"], ingredient_id=flour["id"], amount=500, unit="g"
    )
    [item] = body["extra_items"]
    assert item == {
        "id": item["id"],
        "ingredient_id": flour["id"],
        "text": None,
        "amount": 500,
        "unit": "g",
        "amount_text": None,
        "category_id": None,
        "added_by": ref(anna),
        "created_at": "2026-09-27T12:01:00Z",
    }
    assert uuid.UUID(item["id"]).version == 7
    assert body["version"] == 1

    body = await extra_added(api, anna, shopping_list["id"], ingredient_id=flour["id"], amount=2)
    assert body["extra_items"][1]["unit"] == "piece"  # an amount without a unit
    body = await extra_added(api, anna, shopping_list["id"], ingredient_id=flour["id"])
    assert body["extra_items"][2]["amount"] is None

    body = await extra_added(
        api, anna, shopping_list["id"], text=" Kerzen ", amount_text=" 1 Packung "
    )
    text_item = body["extra_items"][3]
    assert (text_item["text"], text_item["amount_text"]) == ("Kerzen", "1 Packung")
    assert text_item["category_id"] == categories["other"]
    body = await extra_added(
        api,
        anna,
        shopping_list["id"],
        text="Grillkohle",
        amount_text=" ",
        category_id=categories["household_hygiene"],
    )
    last = body["extra_items"][4]
    assert (last["amount_text"], last["category_id"]) == (None, categories["household_hygiene"])
    assert body["version"] == 5


@pytest.mark.parametrize(
    ("body", "problems"),
    [
        ({}, {("body", "text"): "required"}),
        ({"ingredient_id": "{flour}", "text": "x"}, {("body", "text"): "invalid"}),
        ({"ingredient_id": "{flour}", "unit": "g"}, {("body", "amount"): "required"}),
        ({"ingredient_id": "{flour}", "amount_text": "1"}, {("body", "amount_text"): "invalid"}),
        ({"ingredient_id": "{flour}", "category_id": "{other}"},
         {("body", "category_id"): "invalid"}),
        ({"ingredient_id": "unknown"}, {("body", "ingredient_id"): "invalid"}),
        ({"ingredient_id": "{flour}", "amount": 0}, {("body", "amount"): "out_of_range"}),
        ({"ingredient_id": "{flour}", "amount": 100_001}, {("body", "amount"): "out_of_range"}),
        ({"ingredient_id": "{flour}", "unit": "cup", "amount": 1}, {("body", "unit"): "invalid"}),
        ({"text": "x", "amount": 1, "unit": "g"},
         {("body", "amount"): "invalid", ("body", "unit"): "invalid"}),
        ({"text": "x", "category_id": "unknown"}, {("body", "category_id"): "invalid"}),
        ({"text": "  "}, {("body", "text"): "too_short"}),
        ({"text": "x" * 81}, {("body", "text"): "too_long"}),
        ({"text": "a\tb"}, {("body", "text"): "invalid_format"}),
        ({"text": "x", "amount_text": "x" * 31}, {("body", "amount_text"): "too_long"}),
        ({"text": "x", "amount_text": "\x00"}, {("body", "amount_text"): "invalid_format"}),
        ({"text": "x", "id": "not-a-uuid"}, {("body", "id"): "invalid_format"}),
        ({"text": "x", "id": "x" * 46}, {("body", "id"): "too_long"}),
    ],
)  # fmt: skip
async def test_extra_item_validation(
    api: AsyncClient,
    anna: Account,
    flour: Any,
    body: dict[str, Any],
    problems: dict[Any, str],
) -> None:
    other = (await category_ids(api, anna))["other"]
    body = {
        key: value.format(flour=flour["id"], other=other) if isinstance(value, str) else value
        for key, value in body.items()
    }
    shopping_list = await create_list(api, anna)
    response = await add_extra(api, anna, shopping_list["id"], **body)
    assert response.status_code == 422
    assert fields(response) == problems


async def test_client_ids_make_adding_idempotent(
    api: AsyncClient, anna: Account, carl: Account
) -> None:
    """Plan § 5.2: the client may choose the id; sending it again changes nothing."""
    shopping_list = await create_list(api, anna)
    client_id = uuid.uuid4()

    first = await add_extra(api, anna, shopping_list["id"], id=str(client_id).upper(), text="A")
    assert first.status_code == 201
    assert first.json()["extra_items"][0]["id"] == str(client_id)  # canonical spelling
    again = await add_extra(api, anna, shopping_list["id"], id=client_id.urn, text="B")
    assert again.status_code == 200
    assert again.json() == first.json()

    # A deleted item is not brought back by a late retry.
    url = f"/api/lists/{shopping_list['id']}/extra-items/{client_id}"
    assert (await api.delete(url, headers=anna.headers)).status_code == 200
    late = await add_extra(api, anna, shopping_list["id"], id=str(client_id), text="A")
    assert late.status_code == 200
    assert (late.json()["extra_items"], late.json()["version"]) == ([], 2)

    elsewhere = await create_list(api, carl)
    response = await add_extra(api, carl, elsewhere["id"], id=str(client_id), text="A")
    assert response.status_code == 422
    assert fields(response) == {("body", "id"): "taken"}


async def test_update_linked_items(api: AsyncClient, anna: Account, flour: Any, salt: Any) -> None:
    shopping_list = await create_list(api, anna)
    body = await extra_added(
        api, anna, shopping_list["id"], ingredient_id=flour["id"], amount=500, unit="g"
    )
    item_id = body["extra_items"][0]["id"]

    async def update(**changes: Any) -> Any:
        response = await patch_extra(api, anna, shopping_list["id"], item_id, **changes)
        assert response.status_code == 200, response.text
        [item] = response.json()["extra_items"]
        return item["ingredient_id"], item["amount"], item["unit"], response.json()["version"]

    assert await update(amount=750) == (flour["id"], 750, "g", 2)
    assert await update(unit="kg") == (flour["id"], 750, "kg", 3)
    assert await update(amount=750) == (flour["id"], 750, "kg", 3)  # unchanged
    assert await update(amount=None) == (flour["id"], None, None, 4)  # the unit goes too
    assert await update(amount=3) == (flour["id"], 3, "piece", 5)
    assert await update(amount=None, unit=None, ingredient_id=salt["id"]) == (
        salt["id"],
        None,
        None,
        6,
    )

    for changes, problems in (
        ({"unit": "g"}, {("body", "amount"): "required"}),
        ({"text": "x", "amount_text": "1", "category_id": "c"},
         {("body", "text"): "invalid", ("body", "amount_text"): "invalid",
          ("body", "category_id"): "invalid"}),
        ({"ingredient_id": None}, {("body", "ingredient_id"): "invalid"}),
        ({"ingredient_id": "unknown"}, {("body", "ingredient_id"): "invalid"}),
        ({"amount": -1}, {("body", "amount"): "out_of_range"}),
    ):  # fmt: skip
        response = await patch_extra(api, anna, shopping_list["id"], item_id, **changes)
        assert response.status_code == 422, changes
        assert fields(response) == problems


async def test_update_free_text_items(api: AsyncClient, anna: Account, flour: Any) -> None:
    categories = await category_ids(api, anna)
    shopping_list = await create_list(api, anna)
    body = await extra_added(api, anna, shopping_list["id"], text="Kerzen", amount_text="1")
    item_id = body["extra_items"][0]["id"]

    async def update(**changes: Any) -> Any:
        response = await patch_extra(api, anna, shopping_list["id"], item_id, **changes)
        assert response.status_code == 200, response.text
        [item] = response.json()["extra_items"]
        return item["text"], item["amount_text"], item["category_id"], response.json()["version"]

    other, drinks = categories["other"], categories["drinks"]
    assert await update(text=" Wunderkerzen ") == ("Wunderkerzen", "1", other, 2)
    assert await update(amount_text=None) == ("Wunderkerzen", None, other, 3)
    assert await update(category_id=drinks, amount_text="2") == ("Wunderkerzen", "2", drinks, 4)
    assert await update() == ("Wunderkerzen", "2", drinks, 4)

    for changes, problems in (
        ({"ingredient_id": flour["id"], "amount": 1, "unit": "g"},
         {("body", "ingredient_id"): "invalid", ("body", "amount"): "invalid",
          ("body", "unit"): "invalid"}),
        ({"text": None}, {("body", "text"): "invalid"}),
        ({"category_id": None}, {("body", "category_id"): "invalid"}),
        ({"category_id": "unknown"}, {("body", "category_id"): "invalid"}),
    ):  # fmt: skip
        response = await patch_extra(api, anna, shopping_list["id"], item_id, **changes)
        assert response.status_code == 422, changes
        assert fields(response) == problems


async def test_delete_extra_items(api: AsyncClient, anna: Account, carl: Account) -> None:
    shopping_list = await create_list(api, anna)
    other = await create_list(api, carl)
    body = await extra_added(api, anna, shopping_list["id"], text="Kerzen")
    item_id = body["extra_items"][0]["id"]
    url = f"/api/lists/{shopping_list['id']}/extra-items/{item_id}"
    elsewhere = f"/api/lists/{other['id']}/extra-items/{item_id}"
    assert (await api.delete(elsewhere, headers=carl.headers)).status_code == 404
    assert (await api.patch(elsewhere, json={}, headers=carl.headers)).status_code == 404

    response = await api.delete(url, headers=anna.headers)

    assert response.status_code == 200
    assert (response.json()["extra_items"], response.json()["lines"]) == ([], [])
    assert response.json()["version"] == 2
    assert (await api.delete(url, headers=anna.headers)).status_code == 404
    assert (await api.patch(url, json={"text": "x"}, headers=anna.headers)).status_code == 404
    unknown = f"/api/lists/{shopping_list['id']}/extra-items/unknown"
    assert (await api.delete(unknown, headers=anna.headers)).status_code == 404


# --- hidden lines (LIST-07) -----------------------------------------------------------------


async def test_hide_and_restore_lines(api: AsyncClient, anna: Account, flour: Any) -> None:
    shopping_list = await create_list(api, anna)
    await extra_added(api, anna, shopping_list["id"], ingredient_id=flour["id"], amount=1)
    key = f"i:{flour['id']}"

    hidden = await hide(api, anna, shopping_list["id"], key)

    assert hidden.status_code == 200
    assert line(hidden.json(), "Mehl")["hidden"] is True
    assert hidden.json()["version"] == 2
    again = await hide(api, anna, shopping_list["id"], key)
    assert again.json()["version"] == 2  # already hidden
    restored = await hide(api, anna, shopping_list["id"], key, "unhide")
    assert line(restored.json(), "Mehl")["hidden"] is False
    assert restored.json()["version"] == 3
    again = await hide(api, anna, shopping_list["id"], key, "unhide")
    assert again.json()["version"] == 3

    # A key without a line is fine; nothing is stored when restoring it.
    missing = f"x:{uuid.uuid4()}"
    assert (await hide(api, anna, shopping_list["id"], missing, "unhide")).json()["version"] == 3
    assert (await hide(api, anna, shopping_list["id"], missing)).json()["version"] == 4


async def test_a_hidden_key_stays_hidden_when_its_line_appears(
    api: AsyncClient, anna: Account, flour: Any
) -> None:
    shopping_list = await create_list(api, anna)
    await hide(api, anna, shopping_list["id"], f"i:{flour['id']}")
    body = await extra_added(api, anna, shopping_list["id"], ingredient_id=flour["id"])
    assert line(body, "Mehl")["hidden"] is True


@pytest.mark.parametrize(
    "key",
    ["i:abc", f"y:{uuid.uuid4()}", f"i:{str(uuid.uuid4()).upper()}", f"i:{uuid.uuid4()}0"],
)
async def test_line_keys_are_checked(api: AsyncClient, anna: Account, key: str) -> None:
    shopping_list = await create_list(api, anna)
    response = await hide(api, anna, shopping_list["id"], key)
    assert response.status_code == 422
    assert list(fields(response).values()) in (["invalid_format"], ["too_long"])


# --- what each state allows (LIST-10) ------------------------------------------------------


async def test_done_lists_are_read_only_and_lines_are_hidden_in_drafts(
    app: FastAPI, api: AsyncClient, anna: Account, flour: Any
) -> None:
    """Shopping mode (test_shopping.py) keeps meals and extra items editable (LIST-12); a done
    list is read-only; lines are hidden and restored only in a draft (LIST-07)."""
    meal = await create_meal(api, anna, "Brot")
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    [entry] = (await added(api, anna, list_id, meal["id"]))["meals"]
    [item] = (await extra_added(api, anna, list_id, text="Kerzen"))["extra_items"]
    key = f"i:{flour['id']}"
    content = (
        ("POST", "meals", {"meal_id": meal["id"]}),
        ("PATCH", f"meals/{entry['id']}", {"servings": 2}),
        ("DELETE", f"meals/{entry['id']}", None),
        ("POST", "extra-items", {"text": "x"}),
        ("PATCH", f"extra-items/{item['id']}", {"text": "y"}),
        ("DELETE", f"extra-items/{item['id']}", None),
        ("PATCH", "", {"name": "Neu"}),
        ("PATCH", "", {"shared_with_partner": False}),
    )
    lines = (("POST", f"lines/{key}/hide", None), ("POST", f"lines/{key}/unhide", None))

    for status in ("shopping", "done"):
        await set_status(app, list_id, status)
        requests = [(request, "list.not_draft") for request in lines]
        if status == "done":
            requests += [(request, "list.done") for request in content]
        for (method, path, body), code in requests:
            response = await api.request(
                method, f"/api/lists/{list_id}/{path}".rstrip("/"), json=body, headers=anna.headers
            )
            assert response.status_code == 409, (status, method, path)
            assert error(response) == code
        # Copying and deleting work in any state.
        copied = await api.post(f"/api/lists/{list_id}/copy", headers=anna.headers)
        assert copied.json()["list"]["status"] == "draft"
    assert (await detail(api, anna, list_id))["name"] is None
    assert (await api.delete(f"/api/lists/{list_id}", headers=anna.headers)).status_code == 204


# --- copy (VIS-03, VIS-06) ------------------------------------------------------------------


async def test_copy(
    api: AsyncClient,
    anna: Account,
    ben: Account,
    carl: Account,
    clock: FakeClock,
    flour: Any,
) -> None:
    await set_privacy(api, ben, meals_public=False)
    await make_couple(api, anna, ben)
    own = await create_meal(api, anna, "Brot", ingredients=[{"ingredient_id": flour["id"]}])
    partners = await create_meal(api, ben, "Bens Salat")
    gone = await create_meal(api, anna, "Weg")
    shopping_list = await create_list(api, anna, "Wochenende")
    list_id = shopping_list["id"]
    await added(api, anna, list_id, partners["id"], servings=3)
    await added(api, anna, list_id, own["id"], servings=5)
    await added(api, anna, list_id, gone["id"])
    await api.delete(f"/api/meals/{gone['id']}", headers=anna.headers)
    await extra_added(api, anna, list_id, ingredient_id=flour["id"], amount=2, unit="kg")
    [_, deleted] = (await extra_added(api, anna, list_id, text="Weg"))["extra_items"]
    await api.delete(f"/api/lists/{list_id}/extra-items/{deleted['id']}", headers=anna.headers)
    await extra_added(api, anna, list_id, text="Kerzen", amount_text="10")
    await hide(api, anna, list_id, f"i:{flour['id']}")
    clock.advance(minutes=1)

    response = await api.post(f"/api/lists/{list_id}/copy", headers=carl.headers)

    assert response.status_code == 201
    result = response.json()
    assert result["left_out"] == 2  # ben's private meal and the deleted one
    copy = result["list"]
    assert (copy["name"], copy["owner"], copy["is_owner"]) == ("Wochenende", ref(carl), True)
    assert (copy["version"], copy["shared_with_partner"]) == (0, False)
    assert copy["created_at"] == "2026-09-27T12:01:00Z"
    assert [(m["name"], m["servings"], m["meal_id"]) for m in copy["meals"]] == [
        ("Brot", 5, own["id"])
    ]
    items = [(i["ingredient_id"], i["text"], i["amount"], i["unit"], i["amount_text"])
             for i in copy["extra_items"]]  # fmt: skip
    assert items == [(flour["id"], None, 2, "kg", None), (None, "Kerzen", None, None, "10")]
    assert all(item["added_by"] == ref(carl) for item in copy["extra_items"])
    source_ids = {item["id"] for item in (await detail(api, anna, list_id))["extra_items"]}
    assert not source_ids & {item["id"] for item in copy["extra_items"]}
    assert [line["hidden"] for line in copy["lines"]] == [False, False]
    assert await detail(api, carl, copy["id"]) == copy

    # The partner sees ben's meal; their copy is shared with anna (CPL-02).
    partner_copy = (await api.post(f"/api/lists/{list_id}/copy", headers=ben.headers)).json()
    assert partner_copy["left_out"] == 1
    assert [m["name"] for m in partner_copy["list"]["meals"]] == ["Bens Salat", "Brot"]
    assert partner_copy["list"]["shared_with_partner"] is True


async def test_copying_needs_a_visible_list(api: AsyncClient, anna: Account, carl: Account) -> None:
    await set_privacy(api, anna, lists_public=False)
    shopping_list = await create_list(api, anna)
    response = await api.post(f"/api/lists/{shopping_list['id']}/copy", headers=carl.headers)
    assert response.status_code == 404


# --- recently used meals (MEAL-09) ----------------------------------------------------------


async def recent(api: AsyncClient, user: Account) -> list[str]:
    response = await api.get("/api/meals/recent", headers=user.headers)
    assert response.status_code == 200, response.text
    return [meal["name"] for meal in response.json()]


async def test_recently_used_meals(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, clock: FakeClock
) -> None:
    await make_couple(api, anna, ben)
    await set_privacy(api, ben, meals_public=False)
    first = await create_meal(api, anna, "Erstes", tags=["Schnell"])
    second = await create_meal(api, carl, "Zweites")
    partners = await create_meal(api, ben, "Bens")
    gone = await create_meal(api, anna, "Weg")
    lists = [await create_list(api, anna) for _ in range(2)]
    shared = await create_list(api, ben)
    assert await recent(api, anna) == []

    for list_id, meal in (
        (lists[0]["id"], first),
        (lists[0]["id"], second),
        (lists[0]["id"], gone),
        (shared["id"], partners),
        (lists[1]["id"], first),  # used again: first again
    ):
        clock.advance(minutes=1)
        await added(api, anna, list_id, meal["id"])
    await added(api, ben, shared["id"], second["id"])  # ben's use does not count for anna
    await api.delete(f"/api/meals/{gone['id']}", headers=anna.headers)

    response = await api.get("/api/meals/recent", headers=anna.headers)
    [newest, *_] = response.json()
    assert newest["tags"][0]["name"] == "Schnell"  # a full meal summary
    assert await recent(api, anna) == ["Erstes", "Bens", "Zweites"]
    assert await recent(api, ben) == ["Zweites"]

    # Once ben's meals are invisible to anna, they leave her recent meals.
    await api.delete("/api/couple", headers=anna.headers)
    assert await recent(api, anna) == ["Erstes", "Zweites"]


async def test_meals_added_again_are_recent_again(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    """Adding a meal that is on the list already (more servings, LIST-04) counts as using it,
    for whoever added it last (MEAL-09)."""
    await make_couple(api, anna, ben)
    first = await create_meal(api, anna, "Erstes")
    second = await create_meal(api, anna, "Zweites")
    shopping_list = await create_list(api, anna)
    for meal in (first, second, first):
        clock.advance(minutes=1)
        await added(api, anna, shopping_list["id"], meal["id"])
    assert await recent(api, anna) == ["Erstes", "Zweites"]

    clock.advance(minutes=1)
    await added(api, ben, shopping_list["id"], second["id"])
    assert await recent(api, ben) == ["Zweites"]
    assert await recent(api, anna) == ["Erstes"]


async def test_at_most_ten_recent_meals(api: AsyncClient, anna: Account, clock: FakeClock) -> None:
    shopping_list = await create_list(api, anna)
    for index in range(12):
        meal = await create_meal(api, anna, f"Meal {index:02}")
        clock.advance(seconds=1)
        await added(api, anna, shopping_list["id"], meal["id"])
    assert await recent(api, anna) == [f"Meal {index:02}" for index in range(11, 1, -1)]


# --- ETags (plan § 5.8) ---------------------------------------------------------------------


async def test_etags(api: AsyncClient, anna: Account, carl: Account) -> None:
    await set_privacy(api, anna, meals_public=False)
    meal = await create_meal(api, anna, "Geheim")
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal["id"])
    url = f"/api/lists/{shopping_list['id']}"

    response = await api.get(url, headers=anna.headers)

    etag = response.headers["etag"]
    assert etag == f'W/"{hashlib.sha256(response.content).hexdigest()}"'
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["content-type"] == "application/json"
    for tag in (etag, etag.removeprefix("W/"), f'"other", {etag}', "*"):
        unchanged = await api.get(url, headers=anna.headers | {"If-None-Match": tag})
        assert unchanged.status_code == 304, tag
        assert unchanged.content == b""
        assert unchanged.headers["etag"] == etag
    stale = await api.get(url, headers=anna.headers | {"If-None-Match": '"other"'})
    assert (stale.status_code, stale.headers["etag"]) == (200, etag)

    # Specific to the viewer: carl sees a private meal.
    theirs = await api.get(url, headers=carl.headers | {"If-None-Match": etag})
    assert theirs.status_code == 200
    assert theirs.headers["etag"] != etag
    assert theirs.json()["meals"][0]["private"] is True

    # A change of the meal changes the tag, although the list's version stays.
    await api.patch(f"/api/meals/{meal['id']}", json={"name": "Neu"}, headers=anna.headers)
    changed = await api.get(url, headers=anna.headers | {"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.json()["version"] == response.json()["version"]
    assert changed.headers["etag"] != etag


# --- queries per request (PERF) -------------------------------------------------------------


@contextmanager
def counted_queries(app: FastAPI) -> Iterator[list[str]]:
    """The statements the read engine runs meanwhile (authentication included)."""
    database: Database = app.state.database
    statements: list[str] = []

    def record(_conn: Connection, _cursor: object, statement: str, *_: object) -> None:
        statements.append(statement)

    engine = database.read_engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def fill(
    api: AsyncClient, user: Account, list_id: str, ingredients: list[Any], meals: int
) -> None:
    rows = [{"ingredient_id": item["id"], "amount": 10, "unit": "g"} for item in ingredients]
    for index in range(meals):
        meal = await create_meal(api, user, f"Meal {index}", ingredients=rows)
        await added(api, user, list_id, meal["id"])
    for item in ingredients:
        await extra_added(api, user, list_id, ingredient_id=item["id"], amount=1)
        await extra_added(api, user, list_id, text=f"Extra {item['name']}")
        await hide(api, user, list_id, f"i:{item['id']}")
    gone = await create_meal(api, user, "Weg", ingredients=rows)
    await added(api, user, list_id, gone["id"])
    await api.delete(f"/api/meals/{gone['id']}", headers=user.headers)  # a detached meal


async def test_a_list_takes_a_fixed_number_of_queries(
    app: FastAPI, api: AsyncClient, anna: Account, carl: Account
) -> None:
    ingredients = [await create_ingredient(api, anna, f"Zutat {index}") for index in range(20)]
    small = await create_list(api, anna)
    await fill(api, anna, small["id"], ingredients[:1], 1)
    big = await create_list(api, anna)
    await fill(api, anna, big["id"], ingredients, 15)

    with counted_queries(app) as small_detail:
        assert (await get_list(api, carl, small["id"])).status_code == 200
    with counted_queries(app) as big_detail:
        body = (await get_list(api, carl, big["id"])).json()
    assert len(body["lines"]) == 40
    assert len(body["meals"]) == 16
    with counted_queries(app) as summary_queries:
        assert len(await summaries(api, carl)) == 2

    # Authentication, access (the couple once), the eight content queries, visibility and
    # users (two BEGINs).
    assert len(big_detail) == len(small_detail) <= 16
    assert len(summary_queries) <= 17


# --- the polling cache (PERF-02, SYNC-08) ---------------------------------------------------

# What a poll answered from the cache still reads: the authentication.
CACHED_POLL = ["BEGIN", "SELECT"]


def kinds(statements: list[str]) -> list[str]:
    return [statement.split()[0] for statement in statements]


async def poll(
    app: FastAPI, api: AsyncClient, user: Account, list_id: str, etag: str | None = None
) -> tuple[Any, list[str]]:
    """A GET of the list (with `If-None-Match` if given) and the statements it ran."""
    headers = user.headers if etag is None else user.headers | {"If-None-Match": etag}
    with counted_queries(app) as statements:
        response = await api.get(f"/api/lists/{list_id}", headers=headers)
    assert response.status_code in (200, 304), response.text
    return response, kinds(statements)


async def test_polls_are_answered_from_the_cache(
    app: FastAPI, api: AsyncClient, anna: Account, flour: Any
) -> None:
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await extra_added(api, anna, list_id, ingredient_id=flour["id"], amount=500, unit="g")
    database: Database = app.state.database
    generation = database.write_generation

    first, statements = await poll(app, api, anna, list_id)
    assert len(statements) > len(CACHED_POLL)
    etag = first.headers["etag"]
    again, statements = await poll(app, api, anna, list_id)
    assert statements == CACHED_POLL  # the principal is still checked
    assert (again.status_code, again.content, again.headers["etag"]) == (200, first.content, etag)
    assert again.headers["cache-control"] == "no-cache"
    unchanged, statements = await poll(app, api, anna, list_id, etag)
    assert (unchanged.status_code, unchanged.content, statements) == (304, b"", CACHED_POLL)
    assert unchanged.headers["etag"] == etag
    # Reading changes nothing; a refused write neither.
    assert database.write_generation == generation
    response = await patch(api, anna, str(uuid.uuid4()), name="Anders")
    assert response.status_code == 404
    assert (await poll(app, api, anna, list_id))[1] == CACHED_POLL
    # A session that is no longer valid gets no list from the cache.
    await api.post("/api/auth/logout", headers=anna.headers)
    response = await api.get(f"/api/lists/{list_id}", headers=anna.headers)
    assert response.status_code == 401


async def test_any_write_empties_the_cache(
    app: FastAPI, api: AsyncClient, anna: Account, carl: Account
) -> None:
    """Whatever is written may change what someone sees: another list, a privacy switch."""
    meal = await create_meal(api, anna, "Pfannkuchen")
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await added(api, anna, list_id, meal["id"])
    before, _ = await poll(app, api, carl, list_id)
    assert before.json()["meals"][0]["private"] is False

    await create_list(api, carl)
    response, statements = await poll(app, api, carl, list_id, before.headers["etag"])
    assert response.status_code == 304
    assert statements != CACHED_POLL  # built again, with the same result
    await set_privacy(api, anna, meals_public=False)
    response, _ = await poll(app, api, carl, list_id, before.headers["etag"])
    assert response.status_code == 200
    assert response.json()["meals"][0]["private"] is True
    assert (await poll(app, api, carl, list_id))[1] == CACHED_POLL


async def test_cached_lists_expire_after_a_minute(
    app: FastAPI, api: AsyncClient, anna: Account, clock: FakeClock
) -> None:
    """Writes of other processes (CLI commands) do not count, so entries are kept briefly."""
    shopping_list = await create_list(api, anna)
    clock.advance(minutes=1)  # 12:01, the photo URLs of this hour last until 14:00
    await poll(app, api, anna, shopping_list["id"])
    clock.advance(seconds=59)
    assert (await poll(app, api, anna, shopping_list["id"]))[1] == CACHED_POLL
    clock.advance(seconds=1)
    assert (await poll(app, api, anna, shopping_list["id"]))[1] != CACHED_POLL
    assert (await poll(app, api, anna, shopping_list["id"]))[1] == CACHED_POLL


async def test_each_viewer_has_their_own_cached_list(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, carl: Account
) -> None:
    await make_couple(api, anna, ben)
    await set_privacy(api, anna, meals_public=False)
    meal = await create_meal(api, anna, "Geheim")
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await added(api, anna, list_id, meal["id"])

    responses = {}
    for user in (anna, ben, carl, anna, ben, carl):
        response, statements = await poll(app, api, user, list_id)
        assert (statements == CACHED_POLL) is (user.username in responses)
        responses[user.username] = response.json()
    assert [
        (body["is_owner"], body["can_edit"], body["meals"][0]["private"])
        for body in responses.values()
    ] == [(True, True, False), (False, True, False), (False, False, True)]
    # carl's tag is not anna's.
    response, _ = await poll(
        app, api, carl, list_id, (await poll(app, api, anna, list_id))[0].headers["etag"]
    )
    assert response.status_code == 200
    assert response.json()["meals"][0]["private"] is True


async def test_cached_lists_change_with_the_hour_of_their_photo_urls(
    app: FastAPI, api: AsyncClient, anna: Account, clock: FakeClock
) -> None:
    meal = await create_meal(api, anna, "Pfannkuchen")
    await upload(api, anna, meal["id"], jpeg())
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await added(api, anna, list_id, meal["id"])
    clock.advance(minutes=59, seconds=50)  # 12:59:50
    await login(api, anna)
    before, _ = await poll(app, api, anna, list_id)

    clock.advance(seconds=20)  # 13:00:10: the URLs last an hour longer
    after, statements = await poll(app, api, anna, list_id, before.headers["etag"])

    assert (after.status_code, statements != CACHED_POLL) == (200, True)
    old_url, new_url = (item.json()["meals"][0]["thumb_url"] for item in (before, after))
    assert old_url.split("?")[0] == new_url.split("?")[0]
    assert old_url != new_url


async def test_the_cache_keeps_the_most_recently_used_lists(
    app: FastAPI, api: AsyncClient, anna: Account, clock: FakeClock
) -> None:
    app.state.list_cache = ListCache(clock=clock.monotonic, max_entries=2)
    first, second, third = [(await create_list(api, anna))["id"] for _ in range(3)]
    for list_id in (first, second, first, third):
        await poll(app, api, anna, list_id)
    assert (await poll(app, api, anna, first))[1] == CACHED_POLL
    assert (await poll(app, api, anna, third))[1] == CACHED_POLL
    assert (await poll(app, api, anna, second))[1] != CACHED_POLL
    assert len(app.state.list_cache) == 2
