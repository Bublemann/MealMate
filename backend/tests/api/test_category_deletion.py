"""Deleting categories (REF-01, D-30, plan § 6 "Category deleted"): *Uncategorized*, deleted
categories on drafts, lists being shopped and done lists, the protected *Other* and
*Uncategorized*, and the choices that refuse a deleted category."""

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select

from app.models import AdminEvent, ListExtraItem
from tests.accounts import Account, FakeClock, error, fields, make_user, scalars
from tests.catalog import category_ids, create_ingredient
from tests.lists import (
    add_extra,
    added,
    applied,
    create_list,
    detail,
    extra_added,
    op,
    start_shopping,
)
from tests.meals import create_meal


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


@pytest.fixture
async def categories(api: AsyncClient, anna: Account) -> dict[str, str]:
    return await category_ids(api, anna)


@pytest.fixture
async def ingredients(
    api: AsyncClient, anna: Account, categories: dict[str, str]
) -> dict[str, Any]:
    """Onions, minced meat, Gouda (*Cheese*) and salami, by name."""
    specs = {
        "Zwiebeln": "fruit_vegetables",
        "Hackfleisch": "meat_fish",
        "Gouda": "cheese",
        "Salami": "sausage_deli",
    }
    return {
        name: await create_ingredient(api, anna, name, category_id=categories[key])
        for name, key in specs.items()
    }


@pytest.fixture
async def lasagne(api: AsyncClient, anna: Account, ingredients: dict[str, Any]) -> Any:
    """Onions, minced meat and Gouda."""
    return await create_meal(
        api,
        anna,
        "Lasagne",
        servings=2,
        ingredients=[
            {"ingredient_id": ingredients[name]["id"], "amount": amount, "unit": "g"}
            for name, amount in (("Zwiebeln", 300), ("Hackfleisch", 500), ("Gouda", 200))
        ],
    )


async def delete_category(api: AsyncClient, user: Account, category_id: str) -> Response:
    return await api.delete(f"/api/admin/categories/{category_id}", headers=user.headers)


async def deleted(api: AsyncClient, admin: Account, category_id: str) -> None:
    response = await delete_category(api, admin, category_id)
    assert response.status_code == 204, response.text


async def usage(api: AsyncClient, user: Account, category_id: str) -> Response:
    return await api.get(f"/api/admin/categories/{category_id}/usage", headers=user.headers)


async def rename(api: AsyncClient, user: Account, category_id: str, de: str, en: str) -> Response:
    return await api.patch(
        f"/api/admin/categories/{category_id}",
        json={"names": {"de": de, "en": en}},
        headers=user.headers,
    )


async def put_order(api: AsyncClient, user: Account, ids: list[str]) -> Response:
    return await api.put(
        "/api/admin/categories/order", json={"category_ids": ids}, headers=user.headers
    )


async def listed(api: AsyncClient, user: Account) -> list[Any]:
    response = await api.get("/api/categories", headers=user.headers)
    assert response.status_code == 200
    categories: list[Any] = response.json()
    return categories


async def finished(api: AsyncClient, user: Account, list_id: str) -> Any:
    await start_shopping(api, user, list_id)
    return await applied(api, user, list_id, op("list.finish"))


async def delete_extra(api: AsyncClient, user: Account, list_id: str, extra_id: str) -> None:
    response = await api.delete(
        f"/api/lists/{list_id}/extra-items/{extra_id}", headers=user.headers
    )
    assert response.status_code == 200, response.text


def headings(list_detail: Any) -> list[tuple[str, str]]:
    """Each line's name and category id, in the list's order."""
    return [(line["name"], line["category_id"]) for line in list_detail["lines"]]


def extra_categories(list_detail: Any) -> dict[str, str | None]:
    """Each extra item's category id, by its text (free text) or ingredient id (linked)."""
    return {
        item["text"] or item["ingredient_id"]: item["category_id"]
        for item in list_detail["extra_items"]
    }


# --- the category list and its order ---------------------------------------------------------


async def test_the_list_keeps_deleted_categories(
    api: AsyncClient, admin: Account, anna: Account
) -> None:
    """D-30: a deleted category stays in the list with its names, marked as deleted, so old
    lists and the offline copy can still name it. The others close the gap in the walking order;
    the deleted one keeps its last place, after the category that took it over."""
    before = await listed(api, anna)
    assert {item["deleted"] for item in before} == {False}
    keys = [item["key"] for item in before]
    cheese = before[keys.index("cheese")]

    await deleted(api, admin, cheese["id"])

    after = await listed(api, anna)
    assert [item["key"] for item in after] == [*keys[:3], "meat_fish", "cheese", *keys[5:]]
    assert after[4] == {**cheese, "deleted": True}
    shown = [item for item in after if not item["deleted"]]
    assert [item["sort_order"] for item in shown] == list(range(len(shown)))


async def test_the_order_names_every_category_that_isnt_deleted(
    api: AsyncClient, admin: Account, categories: dict[str, str]
) -> None:
    """ADM-01: the order is a permutation of the categories that aren't deleted, *Uncategorized*
    included; the answer is the whole list, as `GET /api/categories` gives it."""
    cheese, uncategorized = categories["cheese"], categories["uncategorized"]
    await deleted(api, admin, cheese)
    shown = [item["id"] for item in await listed(api, admin) if not item["deleted"]]
    others = [category_id for category_id in shown if category_id != uncategorized]

    for refused in ([*shown, cheese], others):
        response = await put_order(api, admin, refused)
        assert response.status_code == 422
        assert fields(response) == {("body", "category_ids"): "invalid"}

    response = await put_order(api, admin, [uncategorized, *others])

    assert response.status_code == 200
    assert response.json() == await listed(api, admin)
    assert [item["id"] for item in response.json() if not item["deleted"]] == [
        uncategorized,
        *others,
    ]


async def test_a_deleted_categorys_names_can_be_used_again(
    api: AsyncClient, admin: Account, categories: dict[str, str]
) -> None:
    """REF-01: names are unique among the categories that aren't deleted, so a section removed by
    mistake can be added again; a new category still goes last."""
    await deleted(api, admin, categories["cheese"])
    shown = [item for item in await listed(api, admin) if not item["deleted"]]

    response = await api.post(
        "/api/admin/categories",
        json={"names": {"de": "Käse", "en": "Cheese"}},
        headers=admin.headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["sort_order"] == len(shown)
    renamed = await rename(api, admin, response.json()["id"], "Käsetheke", "Cheese counter")
    assert renamed.status_code == 200
    again = await rename(api, admin, categories["drinks"], "Käse", "Cheese")
    assert again.status_code == 200


# --- usage and deleting ----------------------------------------------------------------------


async def test_usage_counts_ingredients_and_free_text_items_on_drafts(
    api: AsyncClient, admin: Account, anna: Account, categories: dict[str, str]
) -> None:
    """The delete confirmation (ADM-01) names how many ingredients move to *Uncategorized* and
    how many free-text items on drafts move to *Other*: not deleted ones, nor those on lists
    being shopped or done lists, which stay as they are."""
    cheese = categories["cheese"]
    gouda = await create_ingredient(api, anna, "Gouda", category_id=cheese)
    await create_ingredient(api, anna, "Feta", category_id=cheese)
    await create_ingredient(api, anna, "Milch", category_id=categories["dairy_eggs"])
    draft = await create_list(api, anna)
    await extra_added(api, anna, draft["id"], text="Käsewürfel", category_id=cheese)
    await extra_added(api, anna, draft["id"], ingredient_id=gouda["id"])
    parmesan = str(uuid.uuid7())
    await extra_added(api, anna, draft["id"], id=parmesan, text="Parmesan", category_id=cheese)
    await delete_extra(api, anna, draft["id"], parmesan)
    for state in ("shopping", "done"):
        kept = await create_list(api, anna, state)
        await extra_added(api, anna, kept["id"], text="Käsewürfel", category_id=cheese)
        await (start_shopping if state == "shopping" else finished)(api, anna, kept["id"])

    response = await usage(api, admin, cheese)

    assert response.status_code == 200
    assert response.json() == {"ingredients": 2, "extra_items": 1}
    empty = await usage(api, admin, categories["frozen"])
    assert empty.json() == {"ingredients": 0, "extra_items": 0}


async def test_a_delete_moves_the_ingredients_to_uncategorized(
    api: AsyncClient, admin: Account, anna: Account, categories: dict[str, str], clock: FakeClock
) -> None:
    """REF-01, plan § 6: the category's ingredients go to *Uncategorized*. That isn't an edit of
    theirs, so who changed them last, and when, stays. The activity log records the names and
    both counts (ADM-01)."""
    cheese = categories["cheese"]
    gouda = await create_ingredient(api, anna, "Gouda", category_id=cheese)
    feta = await create_ingredient(api, anna, "Feta", category_id=cheese)
    milk = await create_ingredient(api, anna, "Milch", category_id=categories["dairy_eggs"])
    draft = await create_list(api, anna)
    await extra_added(api, anna, draft["id"], text="Käsewürfel", category_id=cheese)
    clock.advance(minutes=1)

    response = await delete_category(api, admin, cheese)

    assert response.status_code == 204
    uncategorized = categories["uncategorized"]
    for before, category_id in ((gouda, uncategorized), (feta, uncategorized), (milk, None)):
        after = (await api.get(f"/api/ingredients/{before['id']}", headers=anna.headers)).json()
        assert after == {**before, "category_id": category_id or before["category_id"]}
    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert [(event["action"], event["details"], event["target"]) for event in events] == [
        (
            "category.delete",
            {"name_de": "Käse", "name_en": "Cheese", "ingredients": 2, "extra_items": 1},
            None,
        )
    ]
    assert events[0]["actor"]["id"] == admin.id


async def test_free_text_items_on_drafts_move_to_other(
    app: FastAPI, api: AsyncClient, admin: Account, anna: Account, categories: dict[str, str]
) -> None:
    """LIST-06: free-text items in the deleted category move to *Other* on drafts; on lists
    being shopped and done lists they keep it. A deleted item stays as it was."""
    cheese, other, drinks = categories["cheese"], categories["other"], categories["drinks"]
    draft = await create_list(api, anna)
    await extra_added(api, anna, draft["id"], text="Käsewürfel", category_id=cheese)
    await extra_added(api, anna, draft["id"], text="Wasser", category_id=drinks)
    parmesan = str(uuid.uuid7())
    await extra_added(api, anna, draft["id"], id=parmesan, text="Parmesan", category_id=cheese)
    await delete_extra(api, anna, draft["id"], parmesan)
    kept = []
    for state in ("shopping", "done"):
        shopping_list = await create_list(api, anna, state)
        await extra_added(api, anna, shopping_list["id"], text="Käsewürfel", category_id=cheese)
        await (start_shopping if state == "shopping" else finished)(api, anna, shopping_list["id"])
        kept.append(shopping_list["id"])

    await deleted(api, admin, cheese)

    body = await detail(api, anna, draft["id"])
    assert extra_categories(body) == {"Käsewürfel": other, "Wasser": drinks}
    assert headings(body) == [("Wasser", drinks), ("Käsewürfel", other)]
    tombstone = select(ListExtraItem.category_id).where(ListExtraItem.id == parmesan)
    assert await scalars(app, tombstone) == [cheese]
    for list_id in kept:
        body = await detail(api, anna, list_id)
        assert extra_categories(body) == {"Käsewürfel": cheese}
        assert headings(body) == [("Käsewürfel", cheese)]


async def test_lists_being_shopped_and_done_keep_the_deleted_category(
    api: AsyncClient,
    admin: Account,
    anna: Account,
    categories: dict[str, str],
    ingredients: dict[str, Any],
    lasagne: Any,
) -> None:
    """LIST-11, D-30: frozen lines and linked extra items keep a deleted category, with its name
    and near its old place: right after the category that took over its place. Nothing else on
    those lists changes. A draft follows the ingredients into *Uncategorized*, last in the order.
    """
    fruit, meat = categories["fruit_vegetables"], categories["meat_fish"]
    cheese, uncategorized = categories["cheese"], categories["uncategorized"]
    gouda, onions = ingredients["Gouda"], ingredients["Zwiebeln"]
    draft = await create_list(api, anna, "Entwurf")
    await added(api, anna, draft["id"], lasagne["id"])
    shopping = await create_list(api, anna, "Einkauf")
    await added(api, anna, shopping["id"], lasagne["id"])
    await start_shopping(api, anna, shopping["id"])
    done = await create_list(api, anna, "Erledigt")
    for ingredient in (gouda, onions):
        await extra_added(
            api, anna, done["id"], ingredient_id=ingredient["id"], amount=100, unit="g"
        )
    await finished(api, anna, done["id"])
    before = {list_id: await detail(api, anna, list_id) for list_id in (shopping["id"], done["id"])}

    await deleted(api, admin, cheese)

    assert headings(await detail(api, anna, draft["id"])) == [
        ("Zwiebeln", fruit),
        ("Hackfleisch", meat),
        ("Gouda", uncategorized),
    ]
    after = await detail(api, anna, shopping["id"])
    assert headings(after) == [("Zwiebeln", fruit), ("Hackfleisch", meat), ("Gouda", cheese)]
    after_done = await detail(api, anna, done["id"])
    assert headings(after_done) == [("Zwiebeln", fruit), ("Gouda", cheese)]
    for body in (after, after_done):
        old = before[body["id"]]
        assert {line["key"]: line for line in body["lines"]} == {
            line["key"]: line for line in old["lines"]
        }
        assert body["extra_items"] == old["extra_items"]


async def test_draft_lines_come_at_the_place_of_uncategorized(
    api: AsyncClient,
    admin: Account,
    anna: Account,
    categories: dict[str, str],
    lasagne: Any,
) -> None:
    """REF-01: *Uncategorized* is in the walking order like any other category, so the lines of
    the moved ingredients come wherever an admin put it."""
    uncategorized = categories["uncategorized"]
    draft = await create_list(api, anna)
    await added(api, anna, draft["id"], lasagne["id"])
    await deleted(api, admin, categories["cheese"])
    shown = [item["id"] for item in await listed(api, admin) if not item["deleted"]]
    await put_order(api, admin, [uncategorized, *(i for i in shown if i != uncategorized)])

    assert headings(await detail(api, anna, draft["id"])) == [
        ("Gouda", uncategorized),
        ("Zwiebeln", categories["fruit_vegetables"]),
        ("Hackfleisch", categories["meat_fish"]),
    ]


async def test_ties_between_categories_are_broken_the_same_way_every_time(
    api: AsyncClient,
    admin: Account,
    anna: Account,
    categories: dict[str, str],
    ingredients: dict[str, Any],
) -> None:
    """AGG-05: two deleted categories may share their last place with a category that isn't
    deleted: that one comes first, then the deleted ones by id."""
    done = await create_list(api, anna)
    for name in ("Gouda", "Hackfleisch", "Salami"):
        await extra_added(api, anna, done["id"], ingredient_id=ingredients[name]["id"])
    await finished(api, anna, done["id"])

    # Cheese is 4th; once it is deleted, meat & fish takes its place, then sausage & deli.
    await deleted(api, admin, categories["cheese"])
    await deleted(api, admin, categories["meat_fish"])

    first, second = sorted(
        [(categories["cheese"], "Gouda"), (categories["meat_fish"], "Hackfleisch")]
    )
    assert headings(await detail(api, anna, done["id"])) == [
        ("Salami", categories["sausage_deli"]),
        (first[1], first[0]),
        (second[1], second[0]),
    ]


async def test_a_meal_added_while_shopping_freezes_under_its_current_category(
    api: AsyncClient,
    admin: Account,
    anna: Account,
    categories: dict[str, str],
    ingredients: dict[str, Any],
    lasagne: Any,
) -> None:
    """LIST-11: a meal added to a list being shopped is frozen with the ingredients' categories
    at that moment, *Uncategorized* included; a later new category doesn't change it."""
    uncategorized = categories["uncategorized"]
    shopping = await create_list(api, anna)
    await extra_added(api, anna, shopping["id"], text="Kerzen")
    await start_shopping(api, anna, shopping["id"])
    await deleted(api, admin, categories["cheese"])

    body = await added(api, anna, shopping["id"], lasagne["id"])

    assert ("Gouda", uncategorized) in headings(body)
    gouda = ingredients["Gouda"]["id"]
    response = await api.patch(
        f"/api/ingredients/{gouda}",
        json={"category_id": categories["dairy_eggs"]},
        headers=anna.headers,
    )
    assert response.status_code == 200
    assert ("Gouda", uncategorized) in headings(await detail(api, anna, shopping["id"]))


async def test_copies_put_free_text_items_of_a_deleted_category_into_other(
    api: AsyncClient,
    admin: Account,
    anna: Account,
    categories: dict[str, str],
    ingredients: dict[str, Any],
) -> None:
    """LIST-06, SHOP-06, VIS-03: "Shop again" and "Copy" put free-text items whose category was
    deleted into *Other*, and keep the others; the done list keeps the deleted category."""
    cheese, drinks = categories["cheese"], categories["drinks"]
    gouda = ingredients["Gouda"]["id"]
    done = await create_list(api, anna)
    await extra_added(api, anna, done["id"], text="Käsewürfel", category_id=cheese)
    await extra_added(api, anna, done["id"], text="Wasser", category_id=drinks)
    await extra_added(api, anna, done["id"], ingredient_id=gouda, amount=100, unit="g")
    await finished(api, anna, done["id"])
    await deleted(api, admin, cheese)

    for action in ("shop-again", "copy"):
        response = await api.post(f"/api/lists/{done['id']}/{action}", headers=anna.headers)
        assert response.status_code == 201, response.text
        assert extra_categories(response.json()["list"]) == {
            "Käsewürfel": categories["other"],
            "Wasser": drinks,
            gouda: None,
        }
    assert extra_categories(await detail(api, anna, done["id"]))["Käsewürfel"] == cheese


# --- protected and deleted categories --------------------------------------------------------


@pytest.mark.parametrize("key", ["other", "uncategorized"])
async def test_other_and_uncategorized_cannot_be_deleted(
    app: FastAPI, api: AsyncClient, admin: Account, categories: dict[str, str], key: str
) -> None:
    """REF-01: *Other* is the default of new ingredients and free-text items, and *Uncategorized*
    takes a deleted category's ingredients; both always exist."""
    before = await listed(api, admin)

    response = await delete_category(api, admin, categories[key])

    assert response.status_code == 409
    assert error(response) == "category.not_deletable"
    assert await listed(api, admin) == before
    assert await scalars(app, select(AdminEvent.id)) == []


async def test_only_other_can_be_renamed_of_the_two(
    app: FastAPI, api: AsyncClient, admin: Account, categories: dict[str, str]
) -> None:
    """REF-01: *Uncategorized* can only be moved; *Other* can be renamed."""
    response = await rename(api, admin, categories["uncategorized"], "Unsortiert", "Unsorted")

    assert response.status_code == 409
    assert error(response) == "category.not_renamable"
    assert await scalars(app, select(AdminEvent.id)) == []
    renamed = await rename(api, admin, categories["other"], "Diverses", "Sundries")
    assert renamed.status_code == 200


async def test_a_deleted_category_is_not_found(
    api: AsyncClient, admin: Account, categories: dict[str, str]
) -> None:
    """D-30: a deleted category can't be restored, renamed or deleted again."""
    cheese = categories["cheese"]
    await deleted(api, admin, cheese)
    unknown = str(uuid.uuid7())

    for response in (
        await delete_category(api, admin, cheese),
        await rename(api, admin, cheese, "Käse", "Cheese"),
        await usage(api, admin, cheese),
        await delete_category(api, admin, unknown),
        await usage(api, admin, unknown),
    ):
        assert response.status_code == 404
        assert error(response) == "common.not_found"


async def test_only_admins_delete(
    app: FastAPI, api: AsyncClient, anna: Account, categories: dict[str, str]
) -> None:
    before = await listed(api, anna)

    for response in (
        await delete_category(api, anna, categories["cheese"]),
        await usage(api, anna, categories["cheese"]),
    ):
        assert response.status_code == 403
        assert error(response) == "common.forbidden"
    assert await listed(api, anna) == before
    assert await scalars(app, select(AdminEvent.id)) == []


# --- choosing a category ---------------------------------------------------------------------


async def test_ingredients_refuse_a_deleted_category_and_uncategorized(
    api: AsyncClient, admin: Account, anna: Account, categories: dict[str, str]
) -> None:
    """ING-02: a new or changed ingredient can't be put into a deleted category, nor into
    *Uncategorized*, where nothing is put on purpose."""
    milk = await create_ingredient(api, anna, "Milch", category_id=categories["dairy_eggs"])
    await deleted(api, admin, categories["cheese"])

    for category_id in (categories["cheese"], categories["uncategorized"]):
        created = await api.post(
            "/api/ingredients",
            json={"name": "Brie", "category_id": category_id},
            headers=anna.headers,
        )
        updated = await api.patch(
            f"/api/ingredients/{milk['id']}",
            json={"category_id": category_id},
            headers=anna.headers,
        )
        for response in (created, updated):
            assert response.status_code == 422
            assert fields(response) == {("body", "category_id"): "invalid"}


async def test_an_uncategorized_ingredient_can_be_saved_as_it_is(
    api: AsyncClient, admin: Account, anna: Account, categories: dict[str, str]
) -> None:
    """ING-02: an uncategorized ingredient's other fields can be changed without picking a new
    category, also when the form sends the category it has; anyone can give it a new one."""
    uncategorized, dairy = categories["uncategorized"], categories["dairy_eggs"]
    gouda = await create_ingredient(api, anna, "Gouda", category_id=categories["cheese"])
    await deleted(api, admin, categories["cheese"])
    path = f"/api/ingredients/{gouda['id']}"

    for body in (
        {"name": "Gouda jung", "category_id": uncategorized},
        {"nutrients": {"kcal": 356}},
    ):
        response = await api.patch(path, json=body, headers=anna.headers)
        assert response.status_code == 200, response.text
        assert response.json()["category_id"] == uncategorized

    moved = await api.patch(path, json={"category_id": dairy}, headers=anna.headers)
    assert moved.status_code == 200
    assert moved.json()["category_id"] == dairy
    back = await api.patch(path, json={"category_id": uncategorized}, headers=anna.headers)
    assert back.status_code == 422


async def test_free_text_items_refuse_a_deleted_category_and_uncategorized(
    api: AsyncClient, admin: Account, anna: Account, categories: dict[str, str]
) -> None:
    """LIST-06: over the REST API, a free-text item can't be put into a deleted category or
    *Uncategorized*. One that is in a deleted category already (on a list being shopped) keeps
    it when something else changes."""
    cheese, uncategorized = categories["cheese"], categories["uncategorized"]
    draft = await create_list(api, anna)
    candles = str(uuid.uuid7())
    await extra_added(api, anna, draft["id"], id=candles, text="Kerzen")
    shopping = await create_list(api, anna)
    cubes = str(uuid.uuid7())
    await extra_added(api, anna, shopping["id"], id=cubes, text="Käsewürfel", category_id=cheese)
    await start_shopping(api, anna, shopping["id"])
    await deleted(api, admin, cheese)

    for category_id in (cheese, uncategorized):
        created = await add_extra(api, anna, draft["id"], text="Brie", category_id=category_id)
        changed = await api.patch(
            f"/api/lists/{draft['id']}/extra-items/{candles}",
            json={"category_id": category_id},
            headers=anna.headers,
        )
        for response in (created, changed):
            assert response.status_code == 422
            assert fields(response) == {("body", "category_id"): "invalid"}

    response = await api.patch(
        f"/api/lists/{shopping['id']}/extra-items/{cubes}",
        json={"text": "Käsewürfel, groß", "category_id": cheese},
        headers=anna.headers,
    )
    assert response.status_code == 200, response.text
    assert extra_categories(response.json()) == {"Käsewürfel, groß": cheese}


async def test_extra_add_falls_back_to_other(
    api: AsyncClient, admin: Account, anna: Account, categories: dict[str, str]
) -> None:
    """LIST-06, SYNC-04: a free-text item sent after its category was deleted, or in
    *Uncategorized*, lands in *Other*, by id or by an older client's key, so sending it never
    fails."""
    shopping = await create_list(api, anna)
    await start_shopping(api, anna, shopping["id"])
    await deleted(api, admin, categories["cheese"])
    named = {
        "Brie": {"category_id": categories["cheese"]},
        "Camembert": {"category_id": categories["uncategorized"]},
        "Feta": {"category_key": "cheese"},
        "Ziegenkäse": {"category_key": "uncategorized"},
    }

    body = await applied(
        api,
        anna,
        shopping["id"],
        *(
            op("extra.add", extra_id=str(uuid.uuid7()), text=text, **category)
            for text, category in named.items()
        ),
    )

    assert extra_categories(body) == {text: categories["other"] for text in named}
