"""The own walking order of a couple or a user without one (REF-01, D-48): following the
admins' order, an own order and the lists it groups, admins adding and deleting categories, and
couples forming and ending."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from tests.accounts import Account, fields, make_couple, make_user
from tests.catalog import category_ids, create_ingredient
from tests.lists import applied, create_list, detail, extra_added, op, start_shopping


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben")


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


@pytest.fixture
async def groceries(api: AsyncClient, anna: Account) -> Any:
    """Anna's draft with onions (*Fruit & vegetables*), Gouda (*Cheese*) and minced meat
    (*Meat & fish*), which the admins' order has in that order."""
    ids = await category_ids(api, anna)
    draft = await create_list(api, anna, "Wocheneinkauf")
    for name, key in (
        ("Zwiebeln", "fruit_vegetables"),
        ("Hackfleisch", "meat_fish"),
        ("Gouda", "cheese"),
    ):
        ingredient = await create_ingredient(api, anna, name, category_id=ids[key])
        await extra_added(api, anna, draft["id"], ingredient_id=ingredient["id"])
    return draft


async def walking_order(api: AsyncClient, user: Account) -> Any:
    response = await api.get("/api/walking-order", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def admin_categories(api: AsyncClient, user: Account) -> list[Any]:
    """The categories that aren't deleted, in the admins' order."""
    response = await api.get("/api/categories", headers=user.headers)
    assert response.status_code == 200, response.text
    return [item for item in response.json() if not item["deleted"]]


async def keys_to_ids(api: AsyncClient, user: Account) -> dict[str, str]:
    """Key → id of the seeded categories that aren't deleted, in the admins' order."""
    return {item["key"]: item["id"] for item in await admin_categories(api, user)}


async def admin_reordered(api: AsyncClient, admin: Account, category_ids: list[str]) -> None:
    response = await api.put(
        "/api/admin/categories/order", json={"category_ids": category_ids}, headers=admin.headers
    )
    assert response.status_code == 200, response.text


async def created_category(api: AsyncClient, admin: Account, de: str, en: str) -> Any:
    response = await api.post(
        "/api/admin/categories", json={"names": {"de": de, "en": en}}, headers=admin.headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def category_deleted(api: AsyncClient, admin: Account, category_id: str) -> None:
    response = await api.delete(f"/api/admin/categories/{category_id}", headers=admin.headers)
    assert response.status_code == 204, response.text


async def finished(api: AsyncClient, user: Account, list_id: str) -> None:
    await start_shopping(api, user, list_id)
    await applied(api, user, list_id, op("list.finish"))


def keys(order: Any) -> list[str | None]:
    return [item["key"] for item in order["categories"]]


def names(list_detail: Any) -> list[str]:
    """The names of the list's lines, in its order."""
    return [line["name"] for line in list_detail["lines"]]


def moved_first(order: list[str], key: str) -> list[str]:
    return [key, *(each for each in order if each != key)]


async def save(
    api: AsyncClient, user: Account, category_ids: list[str], moved: str | None = None
) -> Response:
    return await api.put(
        "/api/walking-order",
        json={"category_ids": category_ids, "moved_id": moved},
        headers=user.headers,
    )


async def saved(
    api: AsyncClient, user: Account, category_ids: list[str], moved: str | None = None
) -> Any:
    response = await save(api, user, category_ids, moved)
    assert response.status_code == 200, response.text
    return response.json()


# --- following the admins' order -------------------------------------------------------------


async def test_a_new_user_follows_the_admins_order(api: AsyncClient, anna: Account) -> None:
    """D-48: "Reihenfolge der Verwaltung übernehmen" is on by default: the order is the admins'
    one, every category that isn't deleted, *Uncategorized* included, none of them new."""
    order = await walking_order(api, anna)

    assert order == {
        "follows_admin": True,
        "categories": [
            {"id": item["id"], "key": item["key"], "names": item["names"], "new": False}
            for item in await admin_categories(api, anna)
        ],
    }
    assert order["categories"][-1]["key"] == "uncategorized"


async def test_the_walking_order_needs_a_login(api: AsyncClient) -> None:
    response: Response = await api.get("/api/walking-order")
    assert response.status_code == 401


# --- an own order ----------------------------------------------------------------------------


async def test_moving_a_category_saves_an_own_order(api: AsyncClient, anna: Account) -> None:
    """D-48: moving a category turns the switch off and keeps the order as the user's own."""
    ids = await keys_to_ids(api, anna)
    admins = list(ids)
    moved = moved_first(admins, "meat_fish")

    order = await saved(api, anna, [ids[key] for key in moved], moved=ids["meat_fish"])

    assert order["follows_admin"] is False
    assert keys(order) == moved
    assert await walking_order(api, anna) == order


async def test_every_viewer_sees_a_list_in_their_own_order(
    api: AsyncClient, anna: Account, ben: Account, groceries: Any
) -> None:
    """REF-01: every list is grouped in the viewer's order, read-only lists included: Ben sees
    Anna's public list in the admins' order while Anna sees it in hers."""
    ids = await keys_to_ids(api, anna)
    await saved(api, anna, [ids[key] for key in moved_first(list(ids), "meat_fish")])

    assert names(await detail(api, anna, groceries["id"])) == ["Hackfleisch", "Zwiebeln", "Gouda"]
    ben_sees = await detail(api, ben, groceries["id"])
    assert ben_sees["can_edit"] is False
    assert names(ben_sees) == ["Zwiebeln", "Gouda", "Hackfleisch"]


async def test_an_own_order_names_every_category_once(api: AsyncClient, anna: Account) -> None:
    """Like the admins' order: every category that isn't deleted exactly once, *Uncategorized*
    included; the moved one must be one of them. A refused order changes nothing."""
    ids = list((await keys_to_ids(api, anna)).values())
    refused = (
        (ids[1:], None),
        ([*ids, ids[0]], None),
        ([*ids[:-1], ids[0]], None),
        ([*ids[1:], "unknown"], None),
        (ids, "unknown"),
    )

    for order, moved in refused:
        response = await save(api, anna, order, moved)
        assert response.status_code == 422, (order, moved)
        field = "category_ids" if moved is None else "moved_id"
        assert fields(response) == {("body", field): "invalid"}
    assert (await walking_order(api, anna))["follows_admin"] is True


async def test_the_local_copy_is_grouped_in_the_own_order(
    api: AsyncClient, anna: Account, groceries: Any
) -> None:
    """SYNC-02: the phone's local copy is stored in the order the user had then."""
    ids = await keys_to_ids(api, anna)
    await saved(api, anna, [ids[key] for key in moved_first(list(ids), "meat_fish")])

    response = await api.get("/api/lists/sync", headers=anna.headers)

    assert response.status_code == 200, response.text
    [copy] = response.json()["lists"]
    assert names(copy) == ["Hackfleisch", "Zwiebeln", "Gouda"]


# --- the switch "Reihenfolge der Verwaltung übernehmen" --------------------------------------


async def test_while_following_an_admins_reorder_shows_at_once(
    api: AsyncClient, admin: Account, anna: Account, groceries: Any
) -> None:
    """D-48: with the switch on, the admins' order applies live."""
    ids = await keys_to_ids(api, anna)
    await admin_reordered(api, admin, [ids[key] for key in moved_first(list(ids), "meat_fish")])

    assert names(await detail(api, anna, groceries["id"])) == ["Hackfleisch", "Zwiebeln", "Gouda"]
    order = await walking_order(api, anna)
    assert order["follows_admin"] is True
    assert keys(order) == moved_first(list(ids), "meat_fish")


async def test_an_own_order_stays_when_admins_reorder(
    api: AsyncClient, admin: Account, anna: Account, groceries: Any
) -> None:
    """D-48: with the switch off, an admin's reorder doesn't reshuffle the own order."""
    ids = await keys_to_ids(api, anna)
    own = moved_first(list(ids), "cheese")
    await saved(api, anna, [ids[key] for key in own], moved=ids["cheese"])

    await admin_reordered(api, admin, [ids[key] for key in moved_first(list(ids), "meat_fish")])

    assert names(await detail(api, anna, groceries["id"])) == ["Gouda", "Zwiebeln", "Hackfleisch"]
    assert keys(await walking_order(api, anna)) == own


async def test_turning_the_switch_back_on_drops_the_own_order(
    api: AsyncClient, admin: Account, anna: Account, groceries: Any
) -> None:
    """D-48: turning the switch on again drops the own order: the lists follow the admins'
    order again, their later changes included."""
    ids = await keys_to_ids(api, anna)
    await saved(api, anna, [ids[key] for key in moved_first(list(ids), "cheese")])

    response = await api.delete("/api/walking-order", headers=anna.headers)

    assert response.status_code == 204
    assert keys(await walking_order(api, anna)) == list(ids)
    assert (await walking_order(api, anna))["follows_admin"] is True
    assert names(await detail(api, anna, groceries["id"])) == ["Zwiebeln", "Gouda", "Hackfleisch"]
    await admin_reordered(api, admin, [ids[key] for key in moved_first(list(ids), "meat_fish")])
    assert names(await detail(api, anna, groceries["id"])) == ["Hackfleisch", "Zwiebeln", "Gouda"]


async def test_turning_the_switch_off_without_a_move_keeps_the_admins_order(
    api: AsyncClient, admin: Account, anna: Account, groceries: Any
) -> None:
    """Turning the switch off keeps the admins' order as it is as the own order, so admins'
    later changes no longer reach it."""
    ids = await keys_to_ids(api, anna)

    order = await saved(api, anna, list(ids.values()))

    assert order["follows_admin"] is False
    assert keys(order) == list(ids)
    await admin_reordered(api, admin, [ids[key] for key in moved_first(list(ids), "meat_fish")])
    assert names(await detail(api, anna, groceries["id"])) == ["Zwiebeln", "Gouda", "Hackfleisch"]


# --- admins add and delete categories --------------------------------------------------------


async def test_a_new_category_goes_last_in_an_own_order_marked_new(
    api: AsyncClient, admin: Account, anna: Account, ben: Account
) -> None:
    """D-48: a category an admin adds goes to the end of every own order, marked "neu" until it
    is moved; moving another one past it keeps the mark. Without an own order it is simply last
    in the admins' order, and not new."""
    ids = await keys_to_ids(api, anna)
    own = moved_first(list(ids), "cheese")
    await saved(api, anna, [ids[key] for key in own], moved=ids["cheese"])

    bakery = await created_category(api, admin, "Backstube", "Bakehouse")

    anna_order = await walking_order(api, anna)
    assert [item["id"] for item in anna_order["categories"]] == [
        *(ids[key] for key in own),
        bakery["id"],
    ]
    assert [item["id"] for item in anna_order["categories"] if item["new"]] == [bakery["id"]]
    ben_order = await walking_order(api, ben)
    assert ben_order["categories"][-1]["id"] == bakery["id"]
    assert not any(item["new"] for item in ben_order["categories"])

    # Moving "Uncategorized" to the end moves the new category up one, but it stays new.
    shown = [item["id"] for item in anna_order["categories"]]
    swapped = [*shown[:-2], shown[-1], shown[-2]]
    order = await saved(api, anna, swapped, moved=ids["uncategorized"])
    assert [item["id"] for item in order["categories"] if item["new"]] == [bakery["id"]]

    order = await saved(api, anna, [bakery["id"], *swapped[:-2], swapped[-1]], moved=bakery["id"])
    assert order["categories"][0] == {
        "id": bakery["id"],
        "key": None,
        "names": {"de": "Backstube", "en": "Bakehouse"},
        "new": False,
    }


async def test_a_deleted_category_leaves_an_own_order_and_done_lists_keep_its_place(
    api: AsyncClient, admin: Account, anna: Account, ben: Account, groceries: Any
) -> None:
    """D-30, D-48: a deleted category leaves the own order, and the others close the gap. A done
    list keeps showing it near its old place in the viewer's order: right after the category
    that took over its place there. Ben, who follows the admins' order, sees it after the one
    that took over its place in theirs."""
    ids = await keys_to_ids(api, anna)
    own = moved_first(list(ids), "meat_fish")
    await saved(api, anna, [ids[key] for key in own], moved=ids["meat_fish"])
    salami = await create_ingredient(api, anna, "Salami", category_id=ids["sausage_deli"])
    await extra_added(api, anna, groceries["id"], ingredient_id=salami["id"])
    await finished(api, anna, groceries["id"])

    await category_deleted(api, admin, ids["meat_fish"])

    assert keys(await walking_order(api, anna)) == own[1:]
    assert names(await detail(api, anna, groceries["id"])) == [
        "Zwiebeln",
        "Hackfleisch",
        "Gouda",
        "Salami",
    ]
    assert names(await detail(api, ben, groceries["id"])) == [
        "Zwiebeln",
        "Gouda",
        "Salami",
        "Hackfleisch",
    ]


async def test_a_category_deleted_before_the_own_order_keeps_its_old_place(
    api: AsyncClient, admin: Account, anna: Account, groceries: Any
) -> None:
    """D-30: a category deleted while the user followed the admins' order keeps the place it had
    there: in a later own order it comes after the category at that place."""
    ids = await keys_to_ids(api, anna)
    salami = await create_ingredient(api, anna, "Salami", category_id=ids["sausage_deli"])
    await extra_added(api, anna, groceries["id"], ingredient_id=salami["id"])
    await finished(api, anna, groceries["id"])
    await category_deleted(api, admin, ids["meat_fish"])
    shown = [key for key in ids if key != "meat_fish"]

    # Sausage & deli took over the place of meat & fish; now it moves to the top.
    await saved(api, anna, [ids[key] for key in moved_first(shown, "sausage_deli")])

    assert names(await detail(api, anna, groceries["id"])) == [
        "Salami",
        "Zwiebeln",
        "Gouda",
        "Hackfleisch",
    ]


# --- couples ---------------------------------------------------------------------------------


async def test_partners_share_one_order(
    api: AsyncClient, anna: Account, ben: Account, groceries: Any
) -> None:
    """D-48: both partners see and change the same order, so a shared list looks the same for
    both."""
    await make_couple(api, anna, ben)
    response = await api.patch(
        f"/api/lists/{groceries['id']}", json={"shared_with_partner": True}, headers=anna.headers
    )
    assert response.status_code == 200, response.text
    ids = await keys_to_ids(api, anna)
    await saved(api, anna, [ids[key] for key in moved_first(list(ids), "meat_fish")])

    assert await walking_order(api, ben) == await walking_order(api, anna)
    shared = await detail(api, ben, groceries["id"])
    assert shared["can_edit"] is True
    assert names(shared) == ["Hackfleisch", "Zwiebeln", "Gouda"]

    await saved(api, ben, [ids[key] for key in moved_first(list(ids), "cheese")])
    assert keys(await walking_order(api, anna)) == moved_first(list(ids), "cheese")
    assert names(await detail(api, anna, groceries["id"])) == ["Gouda", "Zwiebeln", "Hackfleisch"]

    response = await api.delete("/api/walking-order", headers=ben.headers)
    assert response.status_code == 204
    assert (await walking_order(api, anna))["follows_admin"] is True


async def test_a_new_couple_takes_the_requesters_order(
    api: AsyncClient, anna: Account, ben: Account
) -> None:
    """D-48: when a couple forms and both have an own order, the requester's applies."""
    ids = await keys_to_ids(api, anna)
    anna_order = await saved(api, anna, [ids[key] for key in moved_first(list(ids), "cheese")])
    await saved(api, ben, [ids[key] for key in moved_first(list(ids), "drinks")])

    await make_couple(api, anna, ben)

    assert await walking_order(api, ben) == anna_order
    assert await walking_order(api, anna) == anna_order


async def test_a_new_couple_takes_the_only_own_order(
    api: AsyncClient, anna: Account, ben: Account
) -> None:
    """D-48: if only one of them has an own order, that one applies, the addressee's too."""
    ids = await keys_to_ids(api, anna)
    ben_order = await saved(api, ben, [ids[key] for key in moved_first(list(ids), "drinks")])

    await make_couple(api, anna, ben)

    assert await walking_order(api, anna) == ben_order
    assert await walking_order(api, ben) == ben_order


async def test_a_couple_forming_while_both_follow_the_admins_order_keeps_following(
    api: AsyncClient, anna: Account, ben: Account
) -> None:
    await make_couple(api, anna, ben)

    assert (await walking_order(api, anna))["follows_admin"] is True
    assert (await walking_order(api, ben))["follows_admin"] is True


async def test_each_partner_keeps_the_order_when_the_couple_ends(
    api: AsyncClient, admin: Account, anna: Account, ben: Account
) -> None:
    """D-48: when a couple ends, each partner keeps the order, "neu" marks included; from then on
    each changes their own."""
    await make_couple(api, anna, ben)
    ids = await keys_to_ids(api, anna)
    await saved(api, anna, [ids[key] for key in moved_first(list(ids), "cheese")])
    await created_category(api, admin, "Backstube", "Bakehouse")
    together = await walking_order(api, anna)

    response = await api.delete("/api/couple", headers=ben.headers)
    assert response.status_code == 204

    assert await walking_order(api, anna) == together
    assert await walking_order(api, ben) == together
    response = await api.delete("/api/walking-order", headers=ben.headers)
    assert response.status_code == 204
    assert await walking_order(api, anna) == together
    assert (await walking_order(api, ben))["follows_admin"] is True
