"""Supplies: an item is food or a supply (ING-02, D-56). A supply has no nutrition values and no
piece weight and is never an ingredient in a meal; it can be an extra item or a recurring item.
Open Food Facts never sets the kind."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.accounts import Account, error, fields, make_user, set_privacy
from tests.catalog import EAN_13, NO_NUTRIENTS, create_from_off, create_item
from tests.lists import create_list, detail, extra_added
from tests.meals import create_meal
from tests.recurring import make_recurring


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben")


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


async def post(api: AsyncClient, user: Account, **body: Any) -> Any:
    return await api.post("/api/items", json=body, headers=user.headers)


async def patch(api: AsyncClient, user: Account, item_id: str, **body: Any) -> Any:
    return await api.patch(f"/api/items/{item_id}", json=body, headers=user.headers)


async def get(api: AsyncClient, user: Account, item_id: str) -> Any:
    response = await api.get(f"/api/items/{item_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def found(api: AsyncClient, user: Account, **params: str) -> list[tuple[str, str]]:
    """The search's names and kinds."""
    response = await api.get("/api/items", params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return [(item["name"], item["kind"]) for item in response.json()]


def row(item: Any, amount: float | None = None, unit: str | None = None) -> Any:
    return {"item_id": item["id"], "amount": amount, "unit": unit}


# --- the kind ----------------------------------------------------------------------------------


async def test_a_new_item_is_food(api: AsyncClient, anna: Account) -> None:
    body = await create_item(api, anna, "Milch")
    assert body["kind"] == "food"
    assert await found(api, anna, q="Milch") == [("Milch", "food")]


async def test_a_supply_has_no_nutrients_and_no_piece_weight(
    api: AsyncClient, anna: Account
) -> None:
    body = await create_item(
        api, anna, "Klopapier", kind="supply", base_unit="piece", nutrients=NO_NUTRIENTS
    )

    assert body["kind"] == "supply"
    assert (body["base_unit"], body["piece_weight_g"]) == ("piece", None)
    assert body["nutrients"] == NO_NUTRIENTS
    assert await get(api, anna, body["id"]) == body
    assert await found(api, anna, q="Klopapier") == [("Klopapier", "supply")]


async def test_a_new_supply_refuses_nutrients_and_a_piece_weight(
    api: AsyncClient, anna: Account
) -> None:
    response = await post(
        api,
        anna,
        name="Kerzen",
        kind="supply",
        base_unit="piece",
        piece_weight_g=80,
        nutrients={"kcal": 0, "fat": None},
    )

    assert response.status_code == 422
    assert fields(response) == {
        ("body", "piece_weight_g"): "invalid",
        ("body", "nutrients", "kcal"): "invalid",
    }
    assert await found(api, anna) == []


async def test_a_supply_refuses_nutrients_and_a_piece_weight(
    api: AsyncClient, anna: Account
) -> None:
    candles = await create_item(api, anna, "Kerzen", kind="supply", base_unit="piece")

    response = await patch(api, anna, candles["id"], piece_weight_g=80, nutrients={"kcal": 0})

    assert response.status_code == 422
    assert fields(response) == {
        ("body", "piece_weight_g"): "invalid",
        ("body", "nutrients", "kcal"): "invalid",
    }
    # Switching to food in the same request takes them.
    response = await patch(
        api, anna, candles["id"], kind="food", piece_weight_g=80, nutrients={"kcal": 0}
    )
    assert response.status_code == 200, response.text
    assert response.json()["piece_weight_g"] == 80
    assert response.json()["nutrients"]["kcal"] == 0


async def test_the_kind_cannot_be_null(api: AsyncClient, anna: Account) -> None:
    """Left out or null, a new item is food; an update can't clear the kind."""
    milk = await create_item(api, anna, "Milch", kind=None)
    assert milk["kind"] == "food"
    response = await patch(api, anna, milk["id"], kind=None)
    assert response.status_code == 422
    assert fields(response) == {("body", "kind"): "invalid"}


async def test_a_supply_takes_null_nutrients_without_marking_them(
    api: AsyncClient, anna: Account
) -> None:
    """Null nutrients are fine for a supply, and never count as edited by a user: if it becomes
    food again, a refresh fills them in (BAR-04)."""
    tissues = await create_from_off(
        api,
        anna,
        "Taschentücher",
        EAN_13,
        kind="supply",
        nutrients=NO_NUTRIENTS,
        edited_fields=["name", "nutrients.kcal"],
    )
    assert tissues["user_edited_fields"] == ["name"]

    for nutrients in (None, {"kcal": None}):
        response = await patch(api, anna, tissues["id"], nutrients=nutrients)
        assert response.status_code == 200, response.text
        assert response.json()["user_edited_fields"] == ["name"]
        assert response.json()["nutrients"] == NO_NUTRIENTS


async def test_switching_to_supply_clears_nutrients_and_piece_weight(
    api: AsyncClient, anna: Account
) -> None:
    rolls = await create_item(
        api,
        anna,
        "Klopapier",
        base_unit="piece",
        piece_weight_g=100,
        nutrients={"kcal": 0, "protein": 0},
    )

    response = await patch(api, anna, rolls["id"], kind="supply")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["kind"], body["base_unit"], body["piece_weight_g"]) == ("supply", "piece", None)
    assert body["nutrients"] == NO_NUTRIENTS
    # Back to food, the values are not back.
    body = (await patch(api, anna, rolls["id"], kind="food")).json()
    assert (body["kind"], body["piece_weight_g"], body["nutrients"]) == ("food", None, NO_NUTRIENTS)


async def test_switching_an_off_item_to_supply_drops_its_nutrient_marks(
    api: AsyncClient, anna: Account
) -> None:
    """Its nutrients are no longer the user's: a refresh after switching back to food may fill
    them in again (BAR-04)."""
    tissues = await create_from_off(
        api, anna, "Taschentücher", EAN_13, nutrients={"kcal": 1}, edited_fields=["name"]
    )
    await patch(api, anna, tissues["id"], nutrients={"kcal": 2})

    body = (await patch(api, anna, tissues["id"], kind="supply")).json()

    assert body["user_edited_fields"] == ["name"]
    assert body["nutrients"] == NO_NUTRIENTS


# --- meals (MEAL-02) ---------------------------------------------------------------------------


async def test_switching_to_supply_is_refused_while_meals_use_it(
    api: AsyncClient, anna: Account, ben: Account
) -> None:
    """The refusal counts every meal and names those the user may see, in dictionary order; a
    private meal of someone else is only counted (VIS-02)."""
    paper = await create_item(api, anna, "Küchenpapier", base_unit="piece", nutrients={"kcal": 0})
    await create_meal(api, anna, "Tacos", ingredients=[row(paper)])
    await create_meal(api, anna, "Chili sin Carne", ingredients=[row(paper, 2, "piece")])
    await create_meal(api, ben, "Geheimrezept", ingredients=[row(paper)])
    await set_privacy(api, ben, meals_public=False)
    before = await get(api, anna, paper["id"])

    response = await patch(api, anna, paper["id"], kind="supply", name="Küchenrolle")

    assert response.status_code == 409
    assert error(response) == "item.used_in_meals"
    assert response.json()["params"] == {"meals": 3, "names": ["Chili sin Carne", "Tacos"]}
    assert await get(api, anna, paper["id"]) == before


async def test_a_meal_refuses_a_supply(api: AsyncClient, anna: Account) -> None:
    onions = await create_item(api, anna, "Zwiebeln")
    candles = await create_item(api, anna, "Kerzen", kind="supply")

    response = await api.post(
        "/api/meals",
        json={"name": "Dinner", "ingredients": [row(onions), row(candles)]},
        headers=anna.headers,
    )

    assert response.status_code == 422
    assert fields(response) == {("body", "ingredients", 1, "item_id"): "supply"}

    meal = await create_meal(api, anna, "Dinner", ingredients=[row(onions)])
    response = await api.patch(
        f"/api/meals/{meal['id']}",
        json={"ingredients": [row(candles), row(onions)]},
        headers=anna.headers,
    )
    assert response.status_code == 422
    assert fields(response) == {("body", "ingredients", 0, "item_id"): "supply"}


async def test_the_search_for_food_leaves_supplies_out(api: AsyncClient, anna: Account) -> None:
    """The meal form's item search asks for food only (MEAL-02); everything else finds both."""
    await create_item(api, anna, "Kerzen", kind="supply")
    await create_item(api, anna, "Kekse")

    assert await found(api, anna, q="Ke", kind="food") == [("Kekse", "food")]
    assert await found(api, anna, q="Ke", kind="supply") == [("Kerzen", "supply")]
    assert await found(api, anna, q="Ke") == [("Kekse", "food"), ("Kerzen", "supply")]


async def test_merging_into_a_supply_is_refused_while_meals_use_the_duplicate(
    api: AsyncClient, anna: Account, admin: Account
) -> None:
    paper = await create_item(api, anna, "Küchenpapier")
    roll = await create_item(api, anna, "Küchenrolle", kind="supply")
    await create_meal(api, anna, "Tacos", ingredients=[row(paper)])

    response = await api.post(
        f"/api/admin/items/{paper['id']}/merge",
        json={"into_id": roll["id"]},
        headers=admin.headers,
    )

    assert response.status_code == 409
    assert error(response) == "item.used_in_meals"
    assert response.json()["params"] == {"meals": 1, "names": ["Tacos"]}
    assert (await get(api, anna, paper["id"]))["usage"]["meals"] == 1
    # Not used in meals, it merges.
    unused = await create_item(api, anna, "Küchentücher")
    response = await api.post(
        f"/api/admin/items/{unused['id']}/merge",
        json={"into_id": roll["id"]},
        headers=admin.headers,
    )
    assert response.status_code == 200, response.text


# --- lists (LIST-06, LIST-16) ------------------------------------------------------------------


async def test_a_supply_can_be_an_extra_item_and_a_recurring_item(
    api: AsyncClient, anna: Account
) -> None:
    rolls = await create_item(api, anna, "Klopapier", kind="supply", base_unit="piece")
    draft = await create_list(api, anna)

    await extra_added(api, anna, draft["id"], item_id=rolls["id"], amount=2, unit="piece")
    recurring = await make_recurring(api, anna, rolls["id"])

    extras = (await detail(api, anna, draft["id"]))["extra_items"]
    assert [(extra["item_id"], extra["amount"]) for extra in extras] == [(rolls["id"], 2)]
    assert recurring["item"]["kind"] == "supply"
