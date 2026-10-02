"""The lines of a list: the aggregation service over meals, frozen rows and extra items (AGG,
LIST-04..08, LIST-15, plan § 5.6)."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.accounts import Account, make_user
from tests.catalog import category_ids, create_ingredient, ref
from tests.lists import UNCHECKED, added, create_list, detail, extra_added, line, lines
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
    """Ingredients in four categories, by name."""
    specs: dict[str, dict[str, Any]] = {
        "Zwiebeln": {"category_id": categories["fruit_vegetables"], "piece_weight_g": 150},
        "Mehl": {"category_id": categories["baking"]},
        "Öl": {
            "category_id": categories["sauces_spices_oils"],
            "base_unit": "ml",
            "density_g_per_ml": 0.92,
        },
        "Salz": {"category_id": categories["sauces_spices_oils"]},
        "Brötchen": {"category_id": categories["bread_bakery"]},
    }
    return {name: await create_ingredient(api, anna, name, **body) for name, body in specs.items()}


def row(ingredient: Any, amount: float | None = None, unit: str | None = None) -> dict[str, Any]:
    return {"ingredient_id": ingredient["id"], "amount": amount, "unit": unit}


@pytest.fixture
async def meal_a(api: AsyncClient, anna: Account, ingredients: dict[str, Any]) -> Any:
    """2 servings: 1 onion, 200 g flour, salt to taste."""
    return await create_meal(
        api,
        anna,
        "Zwiebelkuchen",
        servings=2,
        ingredients=[
            row(ingredients["Zwiebeln"], 1, "piece"),
            row(ingredients["Mehl"], 200, "g"),
            row(ingredients["Salz"]),
        ],
    )


@pytest.fixture
async def meal_b(api: AsyncClient, anna: Account, ingredients: dict[str, Any]) -> Any:
    """4 servings: 300 g flour and oil in two rows (2 tbsp + 1 tbsp)."""
    return await create_meal(
        api,
        anna,
        "Brot",
        servings=4,
        ingredients=[
            row(ingredients["Mehl"], 300, "g"),
            row(ingredients["Öl"], 2, "tbsp"),
            row(ingredients["Öl"], 1, "tbsp"),
        ],
    )


async def test_meals_are_scaled_merged_and_sorted(
    api: AsyncClient,
    anna: Account,
    ingredients: dict[str, Any],
    categories: dict[str, str],
    meal_a: Any,
    meal_b: Any,
) -> None:
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal_a["id"], servings=4)
    body = await added(api, anna, shopping_list["id"], meal_b["id"], servings=2)

    # 200 g * 4/2 + 300 g * 2/4 = 550 g; 1 onion * 2; 3 tbsp * 1/2; category order, then name.
    assert lines(body) == {
        "Zwiebeln": ([(2, "piece")], False),
        "Öl": ([(1.5, "tbsp")], False),
        "Salz": ([], True),
        "Mehl": ([(550, "g")], False),
    }
    assert list(lines(body)) == ["Zwiebeln", "Öl", "Salz", "Mehl"]
    [entry_a, entry_b] = body["meals"]
    flour = line(body, "Mehl")
    assert flour == {
        "key": f"i:{ingredients['Mehl']['id']}",
        "kind": "ingredient",
        "ingredient_id": ingredients["Mehl"]["id"],
        "name": "Mehl",
        "brand": None,
        "category_id": categories["baking"],
        "amounts": [{"value": 550, "unit": "g"}],
        "has_unspecified": False,
        "amount_text": None,
        "hidden": False,
        "sources": [
            {
                "kind": "meal",
                "list_meal_id": entry_a["id"],
                "extra_id": None,
                "meal_name": "Zwiebelkuchen",
                "private": False,
                "servings": 4,
                "amount": None,
                "unit": None,
                "amount_text": None,
            },
            {
                "kind": "meal",
                "list_meal_id": entry_b["id"],
                "extra_id": None,
                "meal_name": "Brot",
                "private": False,
                "servings": 2,
                "amount": None,
                "unit": None,
                "amount_text": None,
            },
        ],
        **UNCHECKED,
    }
    # Two rows of one meal are one source.
    assert [source["list_meal_id"] for source in line(body, "Öl")["sources"]] == [entry_b["id"]]


async def test_extra_items(
    api: AsyncClient,
    anna: Account,
    ingredients: dict[str, Any],
    categories: dict[str, str],
    meal_a: Any,
) -> None:
    """LIST-06, AGG-02: linked items merge with their ingredient, free-text items never."""
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await added(api, anna, list_id, meal_a["id"])
    await extra_added(
        api, anna, list_id, ingredient_id=ingredients["Mehl"]["id"], amount=0.8, unit="kg"
    )
    await extra_added(api, anna, list_id, ingredient_id=ingredients["Zwiebeln"]["id"])
    await extra_added(api, anna, list_id, text="Geburtstagskerzen", amount_text="1 Packung")
    await extra_added(api, anna, list_id, text="Geburtstagskerzen")
    body = await extra_added(
        api, anna, list_id, text="Grillkohle", category_id=categories["household_hygiene"]
    )

    assert [(item["name"], item["kind"]) for item in body["lines"]] == [
        ("Zwiebeln", "ingredient"),
        ("Salz", "ingredient"),
        ("Mehl", "ingredient"),
        ("Grillkohle", "text"),
        ("Geburtstagskerzen", "text"),
        ("Geburtstagskerzen", "text"),
    ]
    assert lines(body)["Zwiebeln"] == ([(1, "piece")], True)  # "1 Stk. + some"
    assert lines(body)["Mehl"] == ([(1, "kg")], False)  # 200 g + 0.8 kg
    [flour_item, _, candles, _, coal] = body["extra_items"]
    assert line(body, "Mehl")["sources"][1] == {
        "kind": "extra",
        "list_meal_id": None,
        "extra_id": flour_item["id"],
        "meal_name": None,
        "private": False,
        "servings": None,
        "amount": 0.8,
        "unit": "kg",
        "amount_text": None,
    }
    candle_line = next(item for item in body["lines"] if item["key"] == f"x:{candles['id']}")
    assert candle_line == {
        "key": f"x:{candles['id']}",
        "kind": "text",
        "ingredient_id": None,
        "name": "Geburtstagskerzen",
        "brand": None,
        "category_id": categories["other"],
        "amounts": [],
        "has_unspecified": False,
        "amount_text": "1 Packung",
        "hidden": False,
        "sources": [
            {
                "kind": "extra",
                "list_meal_id": None,
                "extra_id": candles["id"],
                "meal_name": None,
                "private": False,
                "servings": None,
                "amount": None,
                "unit": None,
                "amount_text": "1 Packung",
            }
        ],
        **UNCHECKED,
    }
    assert line(body, "Grillkohle")["category_id"] == coal["category_id"]
    assert candles["added_by"] == ref(anna)


async def test_different_kinds_stay_side_by_side_until_they_convert(
    api: AsyncClient, anna: Account, ingredients: dict[str, Any]
) -> None:
    """AGG-03: "500 g + 2 Stk." while there is no piece weight; merged once there is one."""
    rolls = ingredients["Brötchen"]
    meal = await create_meal(api, anna, "Frühstück", ingredients=[row(rolls, 500, "g")])
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal["id"])
    body = await extra_added(api, anna, shopping_list["id"], ingredient_id=rolls["id"], amount=2)
    assert lines(body)["Brötchen"] == ([(500, "g"), (2, "piece")], False)

    edit = {"piece_weight_g": 50}
    await api.patch(f"/api/ingredients/{rolls['id']}", json=edit, headers=anna.headers)
    assert lines(await detail(api, anna, shopping_list["id"]))["Brötchen"] == ([(600, "g")], False)


async def test_live_meals_follow_their_meal(
    api: AsyncClient, anna: Account, ingredients: dict[str, Any], meal_b: Any
) -> None:
    """LIST-10: a draft is computed from the current meals and ingredients."""
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal_b["id"], servings=2)
    changes = {
        "name": "Weißbrot",
        "servings": 2,
        "ingredients": [row(ingredients["Mehl"], 500, "g")],
    }
    await api.patch(f"/api/meals/{meal_b['id']}", json=changes, headers=anna.headers)
    rename = {"name": "Weizenmehl"}
    await api.patch(
        f"/api/ingredients/{ingredients['Mehl']['id']}", json=rename, headers=anna.headers
    )

    body = await detail(api, anna, shopping_list["id"])

    assert lines(body) == {"Weizenmehl": ([(500, "g")], False)}
    [entry] = body["meals"]
    assert (entry["name"], entry["servings"], entry["meal_servings"]) == ("Weißbrot", 2, 2)
    assert body["version"] == 1  # the list itself did not change


async def test_detached_meals_keep_their_frozen_rows(
    api: AsyncClient, anna: Account, ingredients: dict[str, Any], meal_a: Any
) -> None:
    """LIST-15: a detached meal keeps contributing what it contributed when it went away,
    with the ingredient attributes of that moment; only the servings still scale it."""
    rolls = ingredients["Brötchen"]
    rows = [row(rolls, 2, "piece"), row(rolls, 100, "g")]
    live = await create_meal(api, anna, "Frühstück", ingredients=rows)
    gone = await create_meal(api, anna, "Brunch", servings=2, ingredients=rows)
    live_list = await create_list(api, anna)
    frozen_list = await create_list(api, anna)
    await added(api, anna, live_list["id"], live["id"])
    await added(api, anna, frozen_list["id"], gone["id"], servings=2)
    await added(api, anna, frozen_list["id"], meal_a["id"], servings=2)
    # Renamed and resized after it was added: the frozen copy takes what it is now.
    await api.patch(
        f"/api/meals/{gone['id']}", json={"name": "Großer Brunch", "servings": 4},
        headers=anna.headers,
    )  # fmt: skip
    before = await detail(api, anna, frozen_list["id"])

    assert (await api.delete(f"/api/meals/{gone['id']}", headers=anna.headers)).status_code == 204

    after = await detail(api, anna, frozen_list["id"])
    assert after["lines"] == before["lines"]
    assert after["version"] == before["version"] + 1
    [entry, _] = after["meals"]
    assert entry == {
        "id": entry["id"],
        "meal_id": None,
        "name": "Großer Brunch",
        "private": False,
        "owner": ref(anna),
        "thumb_url": None,
        "servings": 2,
        "meal_servings": 4,
        "detached": "deleted",
    }
    assert lines(after)["Brötchen"] == ([(50, "g"), (1, "piece")], False)

    # A piece weight now merges the live meal's parts, not the frozen ones.
    await api.patch(
        f"/api/ingredients/{rolls['id']}", json={"piece_weight_g": 50}, headers=anna.headers
    )
    assert lines(await detail(api, anna, live_list["id"]))["Brötchen"] == ([(200, "g")], False)
    body = await detail(api, anna, frozen_list["id"])
    assert lines(body)["Brötchen"] == ([(50, "g"), (1, "piece")], False)

    # The servings of a detached meal still scale its rows; removing it takes them away.
    url = f"/api/lists/{frozen_list['id']}/meals/{entry['id']}"
    body = (await api.patch(url, json={"servings": 8}, headers=anna.headers)).json()
    assert lines(body)["Brötchen"] == ([(200, "g"), (4, "piece")], False)
    body = (await api.delete(url, headers=anna.headers)).json()
    assert "Brötchen" not in lines(body)
    assert [meal["name"] for meal in body["meals"]] == ["Zwiebelkuchen"]


async def test_hidden_lines_stay_in_place(
    api: AsyncClient, anna: Account, ingredients: dict[str, Any], meal_a: Any
) -> None:
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal_a["id"])
    key = f"i:{ingredients['Salz']['id']}"
    response = await api.post(
        f"/api/lists/{shopping_list['id']}/lines/{key}/hide", headers=anna.headers
    )
    body = response.json()
    assert [(item["name"], item["hidden"]) for item in body["lines"]] == [
        ("Zwiebeln", False),
        ("Salz", True),
        ("Mehl", False),
    ]


async def test_category_order_follows_the_admin(
    api: AsyncClient,
    anna: Account,
    admin: Account,
    categories: dict[str, str],
    meal_a: Any,
) -> None:
    """REF-01, AGG-05: lines follow the shop's walking order as the admin set it."""
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal_a["id"])
    await extra_added(api, anna, shopping_list["id"], text="Kerzen")
    order = [categories["other"], categories["baking"]] + [
        category_id for key, category_id in categories.items() if key not in {"other", "baking"}
    ]
    response = await api.put(
        "/api/admin/categories/order", json={"category_ids": order}, headers=admin.headers
    )
    assert response.status_code == 200

    body = await detail(api, anna, shopping_list["id"])
    assert list(lines(body)) == ["Kerzen", "Mehl", "Zwiebeln", "Salz"]


async def test_lines_of_a_new_category(
    api: AsyncClient, anna: Account, admin: Account, categories: dict[str, str]
) -> None:
    """REF-01: a category an admin just added takes ingredients and free-text items at once, and
    its lines come at its place in the walking order: last, until it is moved."""
    response = await api.post(
        "/api/admin/categories",
        json={"names": {"de": "Käsetheke", "en": "Cheese counter"}},
        headers=admin.headers,
    )
    counter = response.json()["id"]
    gouda = await create_ingredient(api, anna, "Gouda", category_id=counter)
    shopping_list = await create_list(api, anna)
    await extra_added(
        api, anna, shopping_list["id"], ingredient_id=gouda["id"], amount=200, unit="g"
    )
    await extra_added(api, anna, shopping_list["id"], text="Feta", category_id=counter)
    await extra_added(api, anna, shopping_list["id"], text="Kerzen")

    body = await detail(api, anna, shopping_list["id"])

    assert [(item["name"], item["category_id"]) for item in body["lines"]] == [
        ("Kerzen", categories["other"]),
        ("Feta", counter),
        ("Gouda", counter),
    ]


async def test_lines_are_deterministic(
    api: AsyncClient, anna: Account, ingredients: dict[str, Any], meal_a: Any, meal_b: Any
) -> None:
    """AGG-05: the same content gives the same lines, whatever the order it was added in."""
    first, second = await create_list(api, anna), await create_list(api, anna)
    for list_id, meals, extras in (
        (first["id"], (meal_a, meal_b), ("Kerzen", "Äpfel", "apfel")),
        (second["id"], (meal_b, meal_a), ("apfel", "Äpfel", "Kerzen")),
    ):
        for meal in meals:
            await added(api, anna, list_id, meal["id"])
        for text in extras:
            await extra_added(api, anna, list_id, text=text)
        await extra_added(
            api, anna, list_id, ingredient_id=ingredients["Öl"]["id"], amount=1, unit="l"
        )

    def shown(body: Any) -> list[Any]:
        return [(item["name"], item["amounts"], item["has_unspecified"]) for item in body["lines"]]

    one, other = await detail(api, anna, first["id"]), await detail(api, anna, second["id"])
    assert shown(one) == shown(other)
    names = [item["name"] for item in one["lines"]]
    # By category, then by normalised name ("aepfel" < "apfel" < "kerzen").
    assert names == ["Zwiebeln", "Öl", "Salz", "Mehl", "Äpfel", "apfel", "Kerzen"]
    assert lines(one)["Öl"] == ([(1.05, "l")], False)  # 3 tbsp * 1/1 = 45 ml + 1 l
    assert await detail(api, anna, first["id"]) == one
