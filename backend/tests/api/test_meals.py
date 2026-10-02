"""Meals: create, read, edit, delete, copy, list and filters, visibility and nutrition (MEAL,
VIS-01/02/04, NUT-03..05, CPL-04/06)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import Connection, event, select

from app.db.session import Database
from app.models import Meal, MealIngredient, MealTag, Tag
from app.services import hooks
from tests.accounts import (
    Account,
    FakeClock,
    error,
    fields,
    make_couple,
    make_user,
    scalars,
    set_privacy,
)
from tests.catalog import EAN_13, create_ingredient, ref
from tests.meals import create_meal, get_meal, list_meals, upload

NO_VALUES = {"kcal": None, "protein": None, "carbs": None, "sugar": None, "fat": None}
EMPTY_NUTRITION = {
    "per_meal": NO_VALUES,
    "per_serving": NO_VALUES,
    "incomplete": False,
    "estimate": False,
    "missing": [],
}


def values(kcal: float, protein: float, carbs: float, sugar: float, fat: float) -> Any:
    return {"kcal": kcal, "protein": protein, "carbs": carbs, "sugar": sugar, "fat": fat}


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
async def cuisines(api: AsyncClient, anna: Account) -> dict[str, str]:
    """Cuisine key → id."""
    response = await api.get("/api/cuisines", headers=anna.headers)
    return {item["key"]: item["id"] for item in response.json() if item["key"]}


@pytest.fixture
async def flour(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Mehl", nutrients=values(364, 10, 76, 0.7, 1))


@pytest.fixture
async def salt(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Salz")


def summary(ingredient: Any) -> dict[str, Any]:
    return {
        "id": ingredient["id"],
        "name": ingredient["name"],
        "category_id": ingredient["category_id"],
        "base_unit": ingredient["base_unit"],
        "brand": ingredient["brand"],
        "barcode": ingredient["barcode"],
        "source": ingredient["source"],
    }


async def patch(api: AsyncClient, user: Account, meal_id: str, **body: Any) -> Any:
    return await api.patch(f"/api/meals/{meal_id}", json=body, headers=user.headers)


# --- create and read (MEAL-01, MEAL-02) ----------------------------------------------------------


async def test_create_with_only_a_name(api: AsyncClient, anna: Account) -> None:
    response = await api.post("/api/meals", json={"name": "  Pfannkuchen "}, headers=anna.headers)

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": "Pfannkuchen",
        "owner": ref(anna),
        "is_owner": True,
        "instructions": None,
        "source_url": None,
        "servings": 1,
        "cuisine": None,
        "tags": [],
        "photo": None,
        "ingredients": [],
        "nutrition": EMPTY_NUTRITION,
        "based_on": None,
        "created_at": "2026-09-27T12:00:00Z",
        "updated_at": "2026-09-27T12:00:00Z",
    }
    fetched = await get_meal(api, anna, body["id"])
    assert fetched.status_code == 200
    assert fetched.json() == body


async def test_create_with_everything(
    api: AsyncClient, anna: Account, cuisines: dict[str, str], flour: Any, salt: Any
) -> None:
    eggs = await create_ingredient(api, anna, "Eier", piece_weight_g=60)

    meal = await create_meal(
        api,
        anna,
        "Pfannkuchen",
        instructions="  Rühren.\r\nBacken.\rEssen.  ",
        source_url="  https://example.com/pfannkuchen?x=1#top ",
        servings=2,
        cuisine_id=cuisines["german"],
        tags=["Süß", "  schnell ", "SUESS", "Frühstück"],
        ingredients=[
            {"ingredient_id": flour["id"], "amount": 200, "unit": "g"},
            {"ingredient_id": eggs["id"], "amount": 2},
            {"ingredient_id": salt["id"], "note": " nach Geschmack "},
            {"ingredient_id": flour["id"], "amount": 1, "unit": "tbsp", "note": " "},
        ],
    )

    assert meal["instructions"] == "Rühren.\nBacken.\nEssen."
    assert meal["source_url"] == "https://example.com/pfannkuchen?x=1#top"
    assert meal["servings"] == 2
    assert meal["cuisine"] == {"id": cuisines["german"], "key": "german", "name": None}
    # Deduplicated ignoring case and umlaut spelling (the first spelling wins), by name.
    assert [tag["name"] for tag in meal["tags"]] == ["Frühstück", "schnell", "Süß"]
    rows = [
        (row["position"], row["ingredient"], row["amount"], row["unit"], row["note"])
        for row in meal["ingredients"]
    ]
    assert rows == [
        (0, summary(flour), 200, "g", None),
        (1, summary(eggs), 2, "piece", None),  # an amount without a unit counts as pieces
        (2, summary(salt), None, None, "nach Geschmack"),
        (3, summary(flour), 1, "tbsp", None),  # the same ingredient twice is fine
    ]
    assert len({row["id"] for row in meal["ingredients"]}) == 4
    assert (await get_meal(api, anna, meal["id"])).json() == meal


async def test_tags_are_shared_and_keep_their_first_spelling(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account
) -> None:
    first = await create_meal(api, anna, "Curry", tags=["Vegan"])
    second = await create_meal(api, ben, "Salat", tags=["VEGAN", "Schnell"])

    assert second["tags"] == [{"id": second["tags"][0]["id"], "name": "Schnell"}, first["tags"][0]]
    assert first["tags"][0]["name"] == "Vegan"
    suggestions = await api.get("/api/tags", params={"q": "veg"}, headers=ben.headers)
    assert [tag["name"] for tag in suggestions.json()] == ["Vegan"]
    assert sorted(await scalars(app, select(Tag.name))) == ["Schnell", "Vegan"]


@pytest.mark.parametrize(
    ("body", "problems"),
    [
        ({}, {("body", "name"): "required"}),
        ({"name": "   "}, {("body", "name"): "too_short"}),
        ({"name": "x" * 81}, {("body", "name"): "too_long"}),
        ({"name": "Bell\x07"}, {("body", "name"): "invalid_format"}),
        ({"name": "‮evil"}, {("body", "name"): "invalid_format"}),
        ({"name": "M", "servings": 0}, {("body", "servings"): "out_of_range"}),
        ({"name": "M", "servings": 100}, {("body", "servings"): "out_of_range"}),
        ({"name": "M", "servings": 1.5}, {("body", "servings"): "invalid"}),
        ({"name": "M", "instructions": "a\tb"}, {("body", "instructions"): "invalid_format"}),
        ({"name": "M", "instructions": "a\x00b"}, {("body", "instructions"): "invalid_format"}),
        ({"name": "M", "instructions": "x" * 10_001}, {("body", "instructions"): "too_long"}),
        ({"name": "M", "source_url": "https://e.x/" + "a" * 1990},
         {("body", "source_url"): "too_long"}),
        ({"name": "M", "tags": ["t"] * 11}, {("body", "tags"): "too_long"}),
        ({"name": "M", "tags": ["x" * 31]}, {("body", "tags", 0): "too_long"}),
        ({"name": "M", "tags": ["ok", " "]}, {("body", "tags", 1): "too_short"}),
        ({"name": "M", "cuisine_id": ""}, {("body", "cuisine_id"): "too_short"}),
        ({"name": "M", "ingredients": [{}]},
         {("body", "ingredients", 0, "ingredient_id"): "required"}),
        ({"name": "M", "ingredients": [{"ingredient_id": "i"}] * 101},
         {("body", "ingredients"): "too_long"}),
    ],
)  # fmt: skip
async def test_create_validation(
    api: AsyncClient, anna: Account, body: dict[str, Any], problems: dict[Any, str]
) -> None:
    response = await api.post("/api/meals", json=body, headers=anna.headers)
    assert response.status_code == 422
    assert error(response) == "common.validation"
    assert fields(response) == problems


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "ftp://example.com/x",
        "data:text/html,hi",
        "https://",
        "https:///path",
        "//example.com/x",
        "example.com",
        "http://user:secret@example.com/",
        "http://user@example.com/",
        "https://exa mple.com/",
        "https://example.com/\x00",
        "https://example.com:99999/",
        "http://[::1/",
    ],
)
async def test_source_links_must_be_http_urls(api: AsyncClient, anna: Account, url: str) -> None:
    response = await api.post(
        "/api/meals", json={"name": "M", "source_url": url}, headers=anna.headers
    )
    assert response.status_code == 422
    assert fields(response) == {("body", "source_url"): "invalid_format"}


@pytest.mark.parametrize(
    ("url", "stored"),
    [
        ("HTTPS://Example.com/Rezept", "HTTPS://Example.com/Rezept"),
        ("http://127.0.0.1:8080/x?y=z", "http://127.0.0.1:8080/x?y=z"),
        ("https://bäckerei.example/brötchen", "https://bäckerei.example/brötchen"),
        ("   ", None),
        (None, None),
    ],
)
async def test_valid_source_links(
    api: AsyncClient, anna: Account, url: str | None, stored: str | None
) -> None:
    meal = await create_meal(api, anna, "M", source_url=url)
    assert meal["source_url"] == stored


async def test_row_validation(api: AsyncClient, anna: Account, flour: Any, salt: Any) -> None:
    rows: list[dict[str, Any]] = [
        {"ingredient_id": flour["id"], "unit": "g"},
        {"ingredient_id": "missing", "amount": 1},
        {"ingredient_id": salt["id"], "amount": 0},
        {"ingredient_id": salt["id"], "amount": 100_001},
        {"ingredient_id": salt["id"], "amount": 1, "unit": "cup"},
        {"ingredient_id": salt["id"], "note": "x" * 81},
        {"ingredient_id": salt["id"], "note": "a\nb"},
    ]
    for index, row in enumerate(rows):
        response = await api.post(
            "/api/meals", json={"name": "M", "ingredients": [row]}, headers=anna.headers
        )
        assert response.status_code == 422, index
        assert len(response.json()["fields"]) == 1

    response = await api.post(
        "/api/meals", json={"name": "M", "ingredients": rows[:2]}, headers=anna.headers
    )
    assert fields(response) == {
        ("body", "ingredients", 0, "amount"): "required",
        ("body", "ingredients", 1, "ingredient_id"): "invalid",
    }
    samples = {
        2: "out_of_range",
        3: "out_of_range",
        4: "invalid",
        5: "too_long",
        6: "invalid_format",
    }
    for index, code in samples.items():
        response = await api.post(
            "/api/meals", json={"name": "M", "ingredients": [rows[index]]}, headers=anna.headers
        )
        [(loc, found)] = fields(response).items()
        assert (loc[:3], found) == (("body", "ingredients", 0), code)


async def test_unknown_references_are_reported_together(
    app: FastAPI, api: AsyncClient, anna: Account, salt: Any
) -> None:
    response = await api.post(
        "/api/meals",
        json={
            "name": "M",
            "cuisine_id": "nope",
            "ingredients": [{"ingredient_id": salt["id"], "unit": "g"}, {"ingredient_id": "x"}],
        },
        headers=anna.headers,
    )
    assert fields(response) == {
        ("body", "cuisine_id"): "invalid",
        ("body", "ingredients", 1, "ingredient_id"): "invalid",
        ("body", "ingredients", 0, "amount"): "required",
    }
    assert await scalars(app, select(Meal.id)) == []


async def test_names_may_repeat(api: AsyncClient, anna: Account, ben: Account) -> None:
    await create_meal(api, anna, "Curry")
    await create_meal(api, anna, "curry")
    await create_meal(api, ben, "Curry")
    assert await list_meals(api, anna) == ["Curry", "curry", "Curry"]


# --- nutrition (NUT-03..06) -----------------------------------------------------------------


async def test_nutrition_per_meal_and_per_serving(
    api: AsyncClient, anna: Account, flour: Any, salt: Any
) -> None:
    milk = await create_ingredient(
        api, anna, "Milch", base_unit="ml", nutrients=values(64, 3.4, 4.8, 4.8, 3.5)
    )
    eggs = await create_ingredient(
        api, anna, "Eier", piece_weight_g=60, nutrients=values(155, 13, 1.1, 1.1, 11)
    )
    meal = await create_meal(
        api,
        anna,
        "Pfannkuchen",
        servings=2,
        ingredients=[
            {"ingredient_id": flour["id"], "amount": 200, "unit": "g"},
            {"ingredient_id": milk["id"], "amount": 300, "unit": "ml"},
            {"ingredient_id": eggs["id"], "amount": 2, "unit": "piece"},
            {"ingredient_id": salt["id"], "note": "nach Geschmack"},
        ],
    )

    nutrition = meal["nutrition"]
    assert nutrition["per_meal"] == pytest.approx(values(1106, 45.8, 167.72, 17.12, 25.7))
    assert nutrition["per_serving"] == pytest.approx(values(553, 22.9, 83.86, 8.56, 12.85))
    assert nutrition["incomplete"] is True
    assert nutrition["estimate"] is False
    assert nutrition["missing"] == [
        {
            "ingredient_id": salt["id"],
            "ingredient_name": "Salz",
            "ingredient_brand": None,
            "reason": "no_amount",
            "nutrient": None,
        }
    ]


async def test_nutrition_markers(api: AsyncClient, anna: Account) -> None:
    butter = await create_ingredient(api, anna, "Butter", nutrients=values(741, 0.6, 0.6, 0.6, 82))
    bread = await create_ingredient(api, anna, "Brot", nutrients=values(245, 8.5, 45, 3, 1.6))
    pasta = await create_ingredient(
        api, anna, "Nudeln", brand="Barilla", barcode=EAN_13, nutrients=values(355, 12, 70, 3, 2)
    )

    meal = await create_meal(
        api,
        anna,
        "Brotzeit",
        ingredients=[
            {"ingredient_id": butter["id"], "amount": 1, "unit": "tbsp"},
            {"ingredient_id": bread["id"], "amount": 2, "unit": "piece"},
            {"ingredient_id": pasta["id"], "amount": 100, "unit": "g"},
        ],
    )

    nutrition = meal["nutrition"]
    # Butter: a spoon counted as 15 g (estimate); bread: pieces without a piece weight;
    # pasta: its own values (NUT-02).
    assert nutrition["per_meal"] == pytest.approx(
        values(111.15 + 355, 0.09 + 12, 70.09, 3.09, 14.3)
    )
    assert nutrition["estimate"] is True
    assert nutrition["incomplete"] is True
    assert [(item["ingredient_name"], item["reason"]) for item in nutrition["missing"]] == [
        ("Brot", "not_convertible")
    ]
    assert meal["ingredients"][2]["ingredient"]["brand"] == "Barilla"


async def test_nutrition_of_a_piece_ingredient(api: AsyncClient, anna: Account) -> None:
    """NUT-05: pieces of a Stück ingredient, and an amount without a unit, count with the piece
    weight against the values per 100 g. Without a piece weight they are unknown and named as
    such; other units of a Stück ingredient can't be converted."""
    eggs = await create_ingredient(
        api,
        anna,
        "Eier",
        base_unit="piece",
        piece_weight_g=60,
        nutrients=values(155, 13, 1.1, 1.1, 11),
    )
    rolls = await create_ingredient(
        api, anna, "Brötchen", base_unit="piece", nutrients=values(270, 9, 50, 3, 3)
    )
    meal = await create_meal(
        api,
        anna,
        "Frühstück",
        servings=2,
        ingredients=[
            {"ingredient_id": eggs["id"], "amount": 2, "unit": "piece"},
            {"ingredient_id": eggs["id"], "amount": 1},
            {"ingredient_id": rolls["id"], "amount": 4, "unit": "piece"},
            {"ingredient_id": eggs["id"], "amount": 50, "unit": "g"},
        ],
    )

    nutrition = meal["nutrition"]
    # 3 eggs of 60 g: 180 g.
    assert nutrition["per_meal"] == pytest.approx(values(279, 23.4, 1.98, 1.98, 19.8))
    assert nutrition["per_serving"] == pytest.approx(values(139.5, 11.7, 0.99, 0.99, 9.9))
    assert (nutrition["incomplete"], nutrition["estimate"]) == (True, False)
    assert [(item["ingredient_name"], item["reason"]) for item in nutrition["missing"]] == [
        ("Brötchen", "no_piece_weight"),
        ("Eier", "not_convertible"),
    ]
    assert [(row["amount"], row["unit"]) for row in meal["ingredients"]] == [
        (2, "piece"),
        (1, "piece"),
        (4, "piece"),
        (50, "g"),
    ]

    response = await api.patch(
        f"/api/ingredients/{rolls['id']}", json={"piece_weight_g": 60}, headers=anna.headers
    )
    assert response.status_code == 200
    nutrition = (await get_meal(api, anna, meal["id"])).json()["nutrition"]
    # 4 rolls of 60 g: 240 g more.
    assert nutrition["per_meal"]["kcal"] == pytest.approx(279 + 648)
    assert [item["reason"] for item in nutrition["missing"]] == ["not_convertible"]


async def test_unknown_values_are_listed_per_nutrient(api: AsyncClient, anna: Account) -> None:
    cream = await create_ingredient(api, anna, "Sahne", base_unit="ml", nutrients={"kcal": 300})
    meal = await create_meal(
        api, anna, "Soße", ingredients=[{"ingredient_id": cream["id"], "amount": 0.5, "unit": "l"}]
    )
    nutrition = meal["nutrition"]
    assert nutrition["per_meal"] == {**NO_VALUES, "kcal": 1500}
    assert [(item["reason"], item["nutrient"]) for item in nutrition["missing"]] == [
        ("unknown_value", "protein"),
        ("unknown_value", "carbs"),
        ("unknown_value", "sugar"),
        ("unknown_value", "fat"),
    ]


async def test_nutrition_follows_ingredient_edits(
    api: AsyncClient, anna: Account, ben: Account, flour: Any
) -> None:
    meal = await create_meal(
        api, anna, "Brot", ingredients=[{"ingredient_id": flour["id"], "amount": 500, "unit": "g"}]
    )
    assert meal["nutrition"]["per_meal"]["kcal"] == pytest.approx(1820)

    response = await api.patch(
        f"/api/ingredients/{flour['id']}", json={"nutrients": {"kcal": 350}}, headers=ben.headers
    )
    assert response.status_code == 200
    assert (await get_meal(api, anna, meal["id"])).json()["nutrition"]["per_meal"][
        "kcal"
    ] == pytest.approx(1750)


# --- edit (MEAL-07) ---------------------------------------------------------------------------


async def test_update_changes_only_what_was_sent(
    api: AsyncClient, anna: Account, clock: FakeClock, cuisines: dict[str, str], salt: Any
) -> None:
    meal = await create_meal(
        api,
        anna,
        "Suppe",
        instructions="Kochen.",
        source_url="https://example.com",
        servings=4,
        cuisine_id=cuisines["french"],
        tags=["Warm"],
        ingredients=[{"ingredient_id": salt["id"]}],
    )
    clock.advance(minutes=5)

    response = await patch(api, anna, meal["id"], name="Gemüsesuppe", servings=3)

    assert response.status_code == 200
    updated = response.json()
    assert updated == {
        **meal,
        "name": "Gemüsesuppe",
        "servings": 3,
        "updated_at": "2026-09-27T12:05:00Z",
    }

    cleared = await patch(
        api, anna, meal["id"], instructions=None, source_url=None, cuisine_id=None
    )
    assert cleared.status_code == 200
    body = cleared.json()
    assert (body["instructions"], body["source_url"], body["cuisine"]) == (None, None, None)
    assert body["tags"] == meal["tags"]
    assert body["ingredients"] == meal["ingredients"]


@pytest.mark.parametrize("field", ["name", "servings", "tags", "ingredients"])
async def test_update_refuses_null_for_required_fields(
    api: AsyncClient, anna: Account, field: str
) -> None:
    meal = await create_meal(api, anna, "Suppe")
    response = await patch(api, anna, meal["id"], **{field: None})
    assert response.status_code == 422
    assert fields(response) == {("body", field): "invalid"}


async def test_update_replaces_tags_and_rows(
    app: FastAPI, api: AsyncClient, anna: Account, flour: Any, salt: Any
) -> None:
    meal = await create_meal(
        api,
        anna,
        "Brot",
        tags=["Backen", "Klassiker"],
        ingredients=[
            {"ingredient_id": flour["id"], "amount": 500, "unit": "g"},
            {"ingredient_id": salt["id"], "amount": 10, "unit": "g"},
            {"ingredient_id": salt["id"], "note": "zum Bestreuen"},
        ],
    )
    first, second, _ = (row["id"] for row in meal["ingredients"])

    response = await patch(
        api,
        anna,
        meal["id"],
        tags=["backen", "Sauerteig"],
        ingredients=[
            {"ingredient_id": flour["id"], "amount": 500, "unit": "g"},
            {"ingredient_id": flour["id"], "amount": 50, "unit": "g", "note": "Roggen"},
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert [tag["name"] for tag in body["tags"]] == ["Backen", "Sauerteig"]
    assert [(row["id"], row["amount"], row["note"]) for row in body["ingredients"]] == [
        (first, 500, None),
        (second, 50, "Roggen"),
    ]
    assert len(await scalars(app, select(MealIngredient.id))) == 2

    grown = await patch(
        api,
        anna,
        meal["id"],
        ingredients=[*body_rows(body), {"ingredient_id": salt["id"], "amount": 1, "unit": "tsp"}],
    )
    assert [row["id"] for row in grown.json()["ingredients"]][:2] == [first, second]
    assert len(grown.json()["ingredients"]) == 3

    emptied = await patch(api, anna, meal["id"], tags=[], ingredients=[])
    assert (emptied.json()["tags"], emptied.json()["ingredients"]) == ([], [])
    assert await scalars(app, select(MealTag.meal_id)) == []
    assert await scalars(app, select(MealIngredient.id)) == []
    # Tags stay in the shared pool.
    assert len(await scalars(app, select(Tag.id))) == 3


def body_rows(meal: Any) -> list[dict[str, Any]]:
    return [
        {
            "ingredient_id": row["ingredient"]["id"],
            "amount": row["amount"],
            "unit": row["unit"],
            "note": row["note"],
        }
        for row in meal["ingredients"]
    ]


async def test_update_validation(
    api: AsyncClient, anna: Account, cuisines: dict[str, str], salt: Any
) -> None:
    meal = await create_meal(api, anna, "Suppe", cuisine_id=cuisines["french"])

    response = await patch(
        api,
        anna,
        meal["id"],
        cuisine_id="nope",
        ingredients=[{"ingredient_id": salt["id"], "unit": "g"}],
    )

    assert fields(response) == {
        ("body", "cuisine_id"): "invalid",
        ("body", "ingredients", 0, "amount"): "required",
    }
    assert (await get_meal(api, anna, meal["id"])).json() == meal


# --- visibility and permissions (VIS-01/02/04, CPL-04, SEC-04) --------------------------------


async def test_others_see_public_meals_but_cannot_change_them(
    api: AsyncClient, anna: Account, carl: Account
) -> None:
    meal = await create_meal(api, anna, "Curry")

    seen = await get_meal(api, carl, meal["id"])
    assert seen.status_code == 200
    assert seen.json() == {**meal, "is_owner": False}
    assert await list_meals(api, carl) == ["Curry"]

    for response in (
        await patch(api, carl, meal["id"], name="Mine"),
        await api.delete(f"/api/meals/{meal['id']}", headers=carl.headers),
        await api.delete(f"/api/meals/{meal['id']}/photo", headers=carl.headers),
        await upload(api, carl, meal["id"], b"not even an image"),
    ):
        assert response.status_code == 403
        assert error(response) == "common.forbidden"
    assert (await get_meal(api, anna, meal["id"])).json() == meal


async def test_private_meals_are_hidden_from_everyone_but_the_partner(
    api: AsyncClient, anna: Account, ben: Account, carl: Account
) -> None:
    await make_couple(api, anna, ben)
    meal = await create_meal(api, anna, "Curry")
    await set_privacy(api, anna, meals_public=False)

    assert (await get_meal(api, ben, meal["id"])).status_code == 200
    assert await list_meals(api, ben) == ["Curry"]
    assert await list_meals(api, carl) == []
    missing = await create_meal(api, carl, "Other")
    await api.delete(f"/api/meals/{missing['id']}", headers=carl.headers)
    # Invisible and non-existent meals look the same (no existence leak).
    for meal_id in (meal["id"], missing["id"]):
        for response in (
            await get_meal(api, carl, meal_id),
            await patch(api, carl, meal_id, name="Mine"),
            await api.delete(f"/api/meals/{meal_id}", headers=carl.headers),
            await api.post(f"/api/meals/{meal_id}/copy", headers=carl.headers),
            await api.delete(f"/api/meals/{meal_id}/photo", headers=carl.headers),
            await upload(api, carl, meal_id, b"x"),
        ):
            assert response.status_code == 404
            assert error(response) == "common.not_found"
    # The partner sees it, but only the owner edits it (CPL-06).
    assert (await patch(api, ben, meal["id"], name="Mine")).status_code == 403


async def test_deactivated_owners_meals_stay_visible(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, carl: Account, admin: Account
) -> None:
    dora = await make_user(app, api, "dora")
    await make_couple(api, anna, ben)
    private = await create_meal(api, anna, "Curry")
    await set_privacy(api, anna, meals_public=False)
    public = await create_meal(api, carl, "Chili")
    for user in (anna, carl):
        response = await api.patch(
            f"/api/admin/users/{user.id}", json={"is_active": False}, headers=admin.headers
        )
        assert response.status_code == 200

    seen = await get_meal(api, ben, private["id"])
    assert seen.status_code == 200
    assert seen.json()["owner"] == {**ref(anna), "deactivated": True}
    assert await list_meals(api, ben) == ["Chili", "Curry"]
    assert await list_meals(api, dora) == ["Chili"]
    assert (await get_meal(api, dora, public["id"])).json()["owner"]["deactivated"] is True
    assert (await get_meal(api, dora, private["id"])).status_code == 404


async def test_meal_routes_need_a_token(api: AsyncClient) -> None:
    for method, path in (
        ("GET", "/api/meals"),
        ("GET", "/api/meals/tags"),
        ("POST", "/api/meals"),
        ("GET", "/api/meals/x"),
        ("PATCH", "/api/meals/x"),
        ("DELETE", "/api/meals/x"),
        ("POST", "/api/meals/x/copy"),
        ("PUT", "/api/meals/x/photo"),
        ("DELETE", "/api/meals/x/photo"),
    ):
        response = await api.request(method, path)
        assert response.status_code == 401, (method, path)
        assert error(response) == "common.unauthorized"


# --- delete (MEAL-07) -------------------------------------------------------------------------


async def test_delete(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    carl: Account,
    salt: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def on_meal_deleted(_session: object, meal_id: str, **_: object) -> None:
        calls.append(meal_id)

    monkeypatch.setattr(hooks, "on_meal_deleted", on_meal_deleted)
    meal = await create_meal(
        api, anna, "Curry", tags=["Scharf"], ingredients=[{"ingredient_id": salt["id"]}]
    )
    copy = (await api.post(f"/api/meals/{meal['id']}/copy", headers=carl.headers)).json()

    response = await api.delete(f"/api/meals/{meal['id']}", headers=anna.headers)

    assert response.status_code == 204
    assert calls == [meal["id"]]
    assert (await get_meal(api, anna, meal["id"])).status_code == 404
    assert await scalars(app, select(Meal.id)) == [copy["id"]]
    assert await scalars(app, select(MealIngredient.meal_id)) == [copy["id"]]
    assert await scalars(app, select(MealTag.meal_id)) == [copy["id"]]
    # The copy stays, without its "based on".
    kept = (await get_meal(api, carl, copy["id"])).json()
    assert kept["based_on"] is None
    again = await api.delete(f"/api/meals/{meal['id']}", headers=anna.headers)
    assert again.status_code == 404


async def test_the_real_meal_deleted_hook_runs(api: AsyncClient, anna: Account) -> None:
    meal = await create_meal(api, anna, "Curry")
    assert (await api.delete(f"/api/meals/{meal['id']}", headers=anna.headers)).status_code == 204


async def test_deleting_a_user_deletes_their_meals(
    app: FastAPI, api: AsyncClient, anna: Account, carl: Account, admin: Account
) -> None:
    meal = await create_meal(api, anna, "Curry")
    copy = (await api.post(f"/api/meals/{meal['id']}/copy", headers=carl.headers)).json()

    response = await api.delete(f"/api/admin/users/{anna.id}", headers=admin.headers)

    assert response.status_code == 204
    assert await scalars(app, select(Meal.id)) == [copy["id"]]
    assert (await get_meal(api, carl, copy["id"])).json()["based_on"] is None


# --- copy (MEAL-08) ---------------------------------------------------------------------------


async def test_copy(
    api: AsyncClient,
    anna: Account,
    carl: Account,
    clock: FakeClock,
    cuisines: dict[str, str],
    flour: Any,
    salt: Any,
) -> None:
    meal = await create_meal(
        api,
        anna,
        "Brot",
        instructions="Backen.",
        source_url="https://example.com/brot",
        servings=2,
        cuisine_id=cuisines["german"],
        tags=["Backen"],
        ingredients=[
            {"ingredient_id": flour["id"], "amount": 500, "unit": "g"},
            {"ingredient_id": salt["id"], "note": "eine Prise"},
        ],
    )
    clock.advance(minutes=1)

    response = await api.post(f"/api/meals/{meal['id']}/copy", headers=carl.headers)

    assert response.status_code == 201
    copy = response.json()
    assert copy["id"] != meal["id"]
    assert copy["owner"] == ref(carl)
    assert copy["is_owner"] is True
    assert copy["based_on"] == {"meal_id": meal["id"], "name": "Brot", "owner": ref(anna)}
    assert copy["created_at"] == copy["updated_at"] == "2026-09-27T12:01:00Z"
    same = ("name", "instructions", "source_url", "servings", "cuisine", "tags", "nutrition")
    assert {key: copy[key] for key in same} == {key: meal[key] for key in same}
    assert [{**row, "id": None} for row in copy["ingredients"]] == [
        {**row, "id": None} for row in meal["ingredients"]
    ]
    assert not {row["id"] for row in copy["ingredients"]} & {
        row["id"] for row in meal["ingredients"]
    }
    # Independent: editing the copy leaves the original alone.
    assert (await patch(api, carl, copy["id"], name="Mein Brot")).status_code == 200
    assert (await get_meal(api, anna, meal["id"])).json()["name"] == "Brot"
    assert (await get_meal(api, anna, copy["id"])).json()["based_on"]["name"] == "Brot"


async def test_copying_the_own_meal(api: AsyncClient, anna: Account) -> None:
    meal = await create_meal(api, anna, "Curry")
    response = await api.post(f"/api/meals/{meal['id']}/copy", headers=anna.headers)
    assert response.status_code == 201
    assert response.json()["based_on"]["meal_id"] == meal["id"]
    assert await list_meals(api, anna) == ["Curry", "Curry"]


async def test_based_on_disappears_when_the_original_becomes_invisible(
    api: AsyncClient, anna: Account, ben: Account, carl: Account
) -> None:
    await make_couple(api, anna, ben)
    meal = await create_meal(api, anna, "Curry")
    carls = (await api.post(f"/api/meals/{meal['id']}/copy", headers=carl.headers)).json()
    bens = (await api.post(f"/api/meals/{meal['id']}/copy", headers=ben.headers)).json()

    await set_privacy(api, anna, meals_public=False)

    assert (await get_meal(api, carl, carls["id"])).json()["based_on"] is None
    assert (await get_meal(api, ben, bens["id"])).json()["based_on"]["meal_id"] == meal["id"]
    # Visibility is the viewer's: the partner sees the original behind carl's copy.
    assert (await get_meal(api, ben, carls["id"])).json()["based_on"]["meal_id"] == meal["id"]


# --- list, search and filters (MEAL-09, MEAL-10) ----------------------------------------------


async def test_list(
    api: AsyncClient, anna: Account, ben: Account, cuisines: dict[str, str]
) -> None:
    curry = await create_meal(
        api, anna, "Curry", servings=2, cuisine_id=cuisines["indian"], tags=["Scharf", "Asia"]
    )
    await create_meal(api, ben, "Äpfelkuchen")
    await create_meal(api, anna, "brot")

    response = await api.get("/api/meals", headers=anna.headers)

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Äpfelkuchen", "brot", "Curry"]
    assert response.json()[2] == {
        "id": curry["id"],
        "name": "Curry",
        "owner": ref(anna),
        "cuisine": curry["cuisine"],
        "tags": curry["tags"],
        "servings": 2,
        "thumb_url": None,
        "updated_at": "2026-09-27T12:00:00Z",
    }


async def test_search(api: AsyncClient, anna: Account, cuisines: dict[str, str]) -> None:
    custom = await api.post("/api/cuisines", json={"name": "Fränkisch"}, headers=anna.headers)
    await create_meal(api, anna, "Äpfelkuchen", tags=["Süß"])
    await create_meal(api, anna, "Apfelmus")
    await create_meal(api, anna, "Curry", cuisine_id=cuisines["indian"], tags=["Scharf"])
    await create_meal(api, anna, "Schäufele", cuisine_id=custom.json()["id"])
    await create_meal(api, anna, "Pasta", tags=["Schnell"])

    assert await list_meals(api, anna, q="apfel") == ["Äpfelkuchen", "Apfelmus"]
    assert await list_meals(api, anna, q="ÄPFEL") == ["Äpfelkuchen", "Apfelmus"]
    assert await list_meals(api, anna, q="suess") == ["Äpfelkuchen"]
    assert await list_meals(api, anna, q="sch") == ["Curry", "Pasta", "Schäufele"]
    assert await list_meals(api, anna, q="indi") == ["Curry"]
    assert await list_meals(api, anna, q="frankisch") == ["Schäufele"]
    assert await list_meals(api, anna, q="  ") == [
        "Äpfelkuchen",
        "Apfelmus",
        "Curry",
        "Pasta",
        "Schäufele",
    ]
    assert await list_meals(api, anna, q="nichts") == []


async def test_dictionary_order(api: AsyncClient, anna: Account) -> None:
    """MEAL-09, D-27: Ä sorts as A, so "Äpfel im Schlafrock" sits next to "Apfelstrudel"; real
    letter pairs keep their place ("Feuer" before "Feurige", "Paella" before "Palatschinken")."""
    for name in (
        "Palatschinken",
        "Feurige Nudeln",
        "Apfelstrudel",
        "Paella",
        "Äpfel im Schlafrock",
        "Feuertopf",
        "Ananas-Curry",
    ):
        await create_meal(api, anna, name)

    assert await list_meals(api, anna) == [
        "Ananas-Curry",
        "Äpfel im Schlafrock",
        "Apfelstrudel",
        "Feuertopf",
        "Feurige Nudeln",
        "Paella",
        "Palatschinken",
    ]


async def test_renamed_and_copied_meals_keep_dictionary_order(
    api: AsyncClient, anna: Account
) -> None:
    await create_meal(api, anna, "Apfelstrudel")
    meal = await create_meal(api, anna, "Bratäpfel")
    await create_meal(api, anna, "Ananas-Curry")

    await api.patch(
        f"/api/meals/{meal['id']}", json={"name": "Äpfel im Schlafrock"}, headers=anna.headers
    )
    copy = await api.post(f"/api/meals/{meal['id']}/copy", headers=anna.headers)

    assert copy.status_code == 201
    assert await list_meals(api, anna) == [
        "Ananas-Curry",
        "Äpfel im Schlafrock",
        "Äpfel im Schlafrock",
        "Apfelstrudel",
    ]


async def test_filters(api: AsyncClient, anna: Account, cuisines: dict[str, str]) -> None:
    curry = await create_meal(api, anna, "Curry", cuisine_id=cuisines["indian"], tags=["Scharf"])
    await create_meal(api, anna, "Dal", cuisine_id=cuisines["indian"])
    await create_meal(api, anna, "Chili", tags=["Scharf"])
    tag_id = curry["tags"][0]["id"]

    assert await list_meals(api, anna, cuisine_id=cuisines["indian"]) == ["Curry", "Dal"]
    assert await list_meals(api, anna, tag_id=tag_id) == ["Chili", "Curry"]
    assert await list_meals(api, anna, cuisine_id=cuisines["indian"], tag_id=tag_id) == ["Curry"]
    assert await list_meals(api, anna, cuisine_id=cuisines["thai"]) == []
    assert await list_meals(api, anna, tag_id="unknown") == []


async def test_filter_chips(api: AsyncClient, anna: Account, ben: Account, carl: Account) -> None:
    await create_meal(api, anna, "Anna's")
    await create_meal(api, ben, "Ben's")
    await create_meal(api, carl, "Carl's")
    await set_privacy(api, carl, meals_public=False)

    assert await list_meals(api, anna) == ["Anna's", "Ben's"]
    response = await api.patch(
        "/api/me", json={"filter_hidden": {"meals": [ben.id], "lists": []}}, headers=anna.headers
    )
    assert response.status_code == 200
    assert await list_meals(api, anna) == ["Anna's"]
    # Explicit owners replace the saved chips, but never widen what is visible.
    assert await list_meals(api, anna, owner_ids=[ben.id]) == ["Ben's"]
    assert await list_meals(api, anna, owner_ids=[ben.id, anna.id, carl.id]) == [
        "Anna's",
        "Ben's",
    ]
    assert await list_meals(api, anna, owner_ids=[carl.id]) == []
    assert await list_meals(api, anna, owner_ids=["someone"]) == []
    # Hiding yourself works too.
    await api.patch(
        "/api/me", json={"filter_hidden": {"meals": [anna.id], "lists": []}}, headers=anna.headers
    )
    assert await list_meals(api, anna) == ["Ben's"]


async def meal_tags(api: AsyncClient, user: Account) -> list[str]:
    response = await api.get("/api/meals/tags", headers=user.headers)
    assert response.status_code == 200, response.text
    return [tag["name"] for tag in response.json()]


async def test_meal_tags_are_those_of_visible_meals(
    api: AsyncClient, anna: Account, ben: Account, carl: Account
) -> None:
    await make_couple(api, anna, ben)
    curry = await create_meal(api, anna, "Curry", tags=["Scharf", "Asia"])
    await create_meal(api, anna, "Chili", tags=["scharf"])
    await create_meal(api, ben, "Brot", tags=["Backen", "Asia"])
    await set_privacy(api, ben, meals_public=False)
    await create_meal(api, carl, "Pasta", tags=["Italienisch"])
    gone = await create_meal(api, carl, "Alt", tags=["Vergessen"])
    await api.delete(f"/api/meals/{gone['id']}", headers=carl.headers)

    response = await api.get("/api/meals/tags", headers=anna.headers)
    assert response.status_code == 200
    assert response.json()[0] == curry["tags"][0]
    assert await meal_tags(api, anna) == ["Asia", "Backen", "Italienisch", "Scharf"]
    # A private meal's tags do not leak; a tag no meal uses any more is not offered.
    assert await meal_tags(api, carl) == ["Asia", "Italienisch", "Scharf"]
    # The filter chips narrow the meals, not the tags to filter by.
    await api.patch(
        "/api/me", json={"filter_hidden": {"meals": [carl.id], "lists": []}}, headers=anna.headers
    )
    assert await meal_tags(api, anna) == ["Asia", "Backen", "Italienisch", "Scharf"]
    # The autocomplete keeps the shared pool (REF-04).
    pool = await api.get("/api/tags", params={"q": "verg"}, headers=carl.headers)
    assert [tag["name"] for tag in pool.json()] == ["Vergessen"]


async def test_meal_tags_have_no_limit(api: AsyncClient, anna: Account) -> None:
    names = [f"Tag {index:02}" for index in range(25)]
    for start in range(0, 25, 10):
        await create_meal(api, anna, f"Meal {start}", tags=names[start : start + 10])

    assert await meal_tags(api, anna) == names


async def test_list_validation(api: AsyncClient, anna: Account) -> None:
    response = await api.get("/api/meals", params={"q": "x" * 101}, headers=anna.headers)
    assert fields(response) == {("query", "q"): "too_long"}


# --- queries per request (PERF) -----------------------------------------------------------


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


async def add_meals(
    api: AsyncClient, user: Account, count: int, rows: list[dict[str, Any]], **body: Any
) -> list[Any]:
    return [
        await create_meal(api, user, f"Meal {index}", ingredients=rows, **body)
        for index in range(count)
    ]


async def test_list_and_detail_take_a_fixed_number_of_queries(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    ben: Account,
    cuisines: dict[str, str],
    flour: Any,
    salt: Any,
) -> None:
    rows = [
        {"ingredient_id": flour["id"], "amount": 100, "unit": "g"},
        {"ingredient_id": salt["id"], "amount": 1, "unit": "tsp"},
    ]
    body = {"cuisine_id": cuisines["german"], "tags": ["A", "B"]}
    few = await add_meals(api, anna, 2, rows[:1], **body)

    with counted_queries(app) as small_list:
        assert len(await list_meals(api, ben)) == 2
    with counted_queries(app) as small_detail:
        assert (await get_meal(api, ben, few[0]["id"])).status_code == 200
    with counted_queries(app) as small_tags:
        assert len(await meal_tags(api, ben)) == 2

    many = await add_meals(api, anna, 8, rows * 10, **body)
    copy = (await api.post(f"/api/meals/{many[0]['id']}/copy", headers=ben.headers)).json()
    with counted_queries(app) as big_list:
        assert len(await list_meals(api, ben)) == 11
    with counted_queries(app) as big_detail:
        assert (await get_meal(api, ben, copy["id"])).status_code == 200
    with counted_queries(app) as big_tags:
        assert len(await meal_tags(api, ben)) == 2

    # Authentication, visibility, meals, owners, cuisines and tags (and two BEGINs).
    assert len(big_list) == len(small_list) <= 10
    # The copy's detail also checks its original ("based on"): four queries more at most.
    assert len(small_detail) <= len(big_detail) <= len(small_detail) + 4
    assert len(big_detail) <= 13
    # Authentication, visibility and one query for the tags.
    assert len(big_tags) == len(small_tags) <= 8
