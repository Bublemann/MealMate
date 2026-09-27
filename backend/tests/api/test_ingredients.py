"""Ingredients: create, search, similar hint, edit, nutrition, merge and delete (ING, NUT-02)."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.models import AdminEvent, Ingredient, Product
from app.services import hooks
from tests.accounts import Account, FakeClock, error, fields, make_user, scalars
from tests.catalog import (
    EAN_8,
    EAN_13,
    EAN_13_B,
    NO_NUTRIENTS,
    UPC_A,
    category_ids,
    create_ingredient,
    create_product,
    ref,
    unknown_nutrition,
)


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben")


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


async def patch(api: AsyncClient, user: Account, ingredient_id: str, **body: Any) -> Any:
    return await api.patch(f"/api/ingredients/{ingredient_id}", json=body, headers=user.headers)


async def search(api: AsyncClient, user: Account, **params: str) -> list[str]:
    response = await api.get("/api/ingredients", params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()]


# --- create and read (ING-01, ING-02) ----------------------------------------------------------


async def test_create_with_defaults(api: AsyncClient, anna: Account) -> None:
    categories = await category_ids(api, anna)

    response = await api.post("/api/ingredients", json={"name": "  Äpfel "}, headers=anna.headers)

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "name": "Äpfel",
        "category_id": categories["other"],
        "base_unit": "g",
        "piece_weight_g": None,
        "density_g_per_ml": None,
        "manual": NO_NUTRIENTS,
        "nutrition": unknown_nutrition(),
        "product_count": 0,
        "created_by": ref(anna),
        "updated_by": ref(anna),
        "created_at": "2026-09-27T12:00:00Z",
        "updated_at": "2026-09-27T12:00:00Z",
    }
    fetched = await api.get(f"/api/ingredients/{body['id']}", headers=anna.headers)
    assert fetched.status_code == 200
    assert fetched.json() == body


async def test_create_with_everything(api: AsyncClient, anna: Account) -> None:
    categories = await category_ids(api, anna)
    body = await create_ingredient(
        api,
        anna,
        "Milch",
        category_id=categories["dairy_eggs"],
        base_unit="ml",
        piece_weight_g=1030,
        density_g_per_ml=1.03,
        manual={"kcal": 64, "fat": 3.5},
    )
    assert body["category_id"] == categories["dairy_eggs"]
    assert (body["base_unit"], body["piece_weight_g"], body["density_g_per_ml"]) == (
        "ml",
        1030,
        1.03,
    )
    assert body["manual"] == NO_NUTRIENTS | {"kcal": 64, "fat": 3.5}
    assert body["nutrition"]["kcal"] == {
        "value": 64,
        "source": "manual",
        "products_mean": None,
        "products_count": 0,
    }
    assert body["nutrition"]["protein"]["source"] == "unknown"


async def test_names_are_unique_ignoring_case_and_umlauts(api: AsyncClient, anna: Account) -> None:
    await create_ingredient(api, anna, "Äpfel")
    response = await api.post(
        "/api/ingredients",
        json={"name": "AEPFEL", "category_id": "unknown"},
        headers=anna.headers,
    )
    assert response.status_code == 422
    assert error(response) == "common.validation"
    assert fields(response) == {("body", "name"): "taken", ("body", "category_id"): "invalid"}


@pytest.mark.parametrize(
    ("body", "field", "code"),
    [
        ({"name": ""}, "name", "too_short"),
        ({"name": "   "}, "name", "too_short"),
        ({"name": "x" * 61}, "name", "too_long"),
        ({"name": "Äpfel‮"}, "name", "invalid_format"),
        ({"name": "Äp\nfel"}, "name", "invalid_format"),
        ({"name": "́"}, "name", "invalid_format"),
        ({"base_unit": "kg"}, "base_unit", "invalid"),
        ({"piece_weight_g": 0}, "piece_weight_g", "out_of_range"),
        ({"piece_weight_g": 10_000.5}, "piece_weight_g", "out_of_range"),
        ({"density_g_per_ml": 0.09}, "density_g_per_ml", "out_of_range"),
        ({"density_g_per_ml": 5.01}, "density_g_per_ml", "out_of_range"),
    ],
)
async def test_invalid_fields(
    api: AsyncClient, anna: Account, body: dict[str, Any], field: str, code: str
) -> None:
    response = await api.post(
        "/api/ingredients", json={"name": "Äpfel", **body}, headers=anna.headers
    )
    assert response.status_code == 422
    assert fields(response) == {("body", field): code}


@pytest.mark.parametrize(
    ("manual", "field"),
    [
        ({"kcal": 900.5}, "kcal"),
        ({"kcal": -1}, "kcal"),
        ({"protein": 100.1}, "protein"),
        ({"carbs": 101}, "carbs"),
        ({"sugar": -0.1}, "sugar"),
        ({"fat": 1000}, "fat"),
    ],
)
async def test_implausible_nutrients(
    api: AsyncClient, anna: Account, manual: dict[str, float], field: str
) -> None:
    response = await api.post(
        "/api/ingredients", json={"name": "Äpfel", "manual": manual}, headers=anna.headers
    )
    assert fields(response) == {("body", "manual", field): "out_of_range"}


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize(
    ("body", "loc"),
    [
        ('{{"name": "Äpfel", "piece_weight_g": {value}}}', ("body", "piece_weight_g")),
        ('{{"name": "Äpfel", "manual": {{"kcal": {value}}}}}', ("body", "manual", "kcal")),
    ],
    ids=["piece_weight_g", "manual.kcal"],
)
async def test_numbers_must_be_finite(
    api: AsyncClient, anna: Account, value: str, body: str, loc: tuple[str, ...]
) -> None:
    """JSON bodies may spell NaN and Infinity; such numbers are out of range."""
    response = await api.post(
        "/api/ingredients",
        content=body.format(value=value).encode(),
        headers=anna.headers | {"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert fields(response) == {loc: "out_of_range"}


async def test_limits_are_inclusive(api: AsyncClient, anna: Account) -> None:
    body = await create_ingredient(
        api,
        anna,
        "Grenzfall",
        piece_weight_g=10_000,
        density_g_per_ml=5,
        manual={"kcal": 900, "protein": 0, "carbs": 100, "sugar": 100, "fat": 100},
    )
    assert body["manual"] == {"kcal": 900, "protein": 0, "carbs": 100, "sugar": 100, "fat": 100}
    other = await create_ingredient(api, anna, "Leicht", density_g_per_ml=0.1)
    assert other["density_g_per_ml"] == 0.1


async def test_unknown_ingredient(api: AsyncClient, anna: Account) -> None:
    for response in (
        await api.get("/api/ingredients/nope", headers=anna.headers),
        await patch(api, anna, "nope", name="x"),
        await api.get("/api/ingredients/nope/products", headers=anna.headers),
    ):
        assert response.status_code == 404
        assert error(response) == "common.not_found"


# --- search and the similar hint (ING-03) ------------------------------------------------------


async def test_search_ignores_case_umlauts_and_accents(api: AsyncClient, anna: Account) -> None:
    for name in ("Äpfel", "Crème fraîche", "Birnen", "Apfelmus"):
        await create_ingredient(api, anna, name)

    for query in ("apfel", "Äpfel", "aepfel", "ÄPF"):
        assert "Äpfel" in await search(api, anna, q=query), query
    # "aepfel" and "apfel" are the same search (ING-03).
    assert await search(api, anna, q="aepfel") == ["Äpfel", "Apfelmus"]
    assert await search(api, anna, q="creme") == ["Crème fraîche"]
    assert await search(api, anna, q="FRAICHE") == ["Crème fraîche"]
    assert await search(api, anna, q="zzz") == []


async def test_search_puts_prefix_matches_first(api: AsyncClient, anna: Account) -> None:
    for name in ("Passierte Tomaten", "Tomatenmark", "Tomaten", "Getrocknete Tomaten"):
        await create_ingredient(api, anna, name)
    assert await search(api, anna, q="toma") == [
        "Tomaten",
        "Tomatenmark",
        "Getrocknete Tomaten",
        "Passierte Tomaten",
    ]


async def test_list_by_category_order_then_name(api: AsyncClient, anna: Account) -> None:
    categories = await category_ids(api, anna)
    await create_ingredient(api, anna, "Salz", category_id=categories["sauces_spices_oils"])
    await create_ingredient(api, anna, "Zwiebeln", category_id=categories["fruit_vegetables"])
    await create_ingredient(api, anna, "Äpfel", category_id=categories["fruit_vegetables"])
    await create_ingredient(api, anna, "Alufolie")
    await create_ingredient(api, anna, "Gouda", category_id=categories["cheese"])

    assert await search(api, anna) == ["Äpfel", "Zwiebeln", "Gouda", "Salz", "Alufolie"]
    assert await search(api, anna, q="  ") == await search(api, anna)
    fruit = categories["fruit_vegetables"]
    assert await search(api, anna, category_id=fruit) == ["Äpfel", "Zwiebeln"]
    assert await search(api, anna, category_id=fruit, q="zw") == ["Zwiebeln"]
    assert await search(api, anna, category_id="unknown") == []


async def test_summaries(api: AsyncClient, anna: Account) -> None:
    milk = await create_ingredient(api, anna, "Milch", base_unit="ml")
    await create_product(api, anna, milk["id"], EAN_13)
    await create_product(api, anna, milk["id"], EAN_8)
    response = await api.get("/api/ingredients", params={"q": "milch"}, headers=anna.headers)
    assert response.json() == [
        {
            "id": milk["id"],
            "name": "Milch",
            "category_id": milk["category_id"],
            "base_unit": "ml",
            "product_count": 2,
        }
    ]


async def test_similar_ingredients(api: AsyncClient, anna: Account) -> None:
    for name in ("Äpfel", "Apfelmus", "Birnen", "Tomaten", "Tomate getrocknet"):
        await create_ingredient(api, anna, name)

    async def similar(name: str) -> list[str]:
        response = await api.get(
            "/api/ingredients/similar", params={"name": name}, headers=anna.headers
        )
        assert response.status_code == 200
        return [item["name"] for item in response.json()]

    assert await similar("Apfel") == ["Äpfel", "Apfelmus"]
    assert await similar("äpfel") == ["Äpfel", "Apfelmus"]
    assert await similar("Tomate") == ["Tomaten", "Tomate getrocknet"]
    assert await similar("Birne") == ["Birnen"]
    assert await similar("Gurke") == []
    assert await similar("  ") == []
    response = await api.get("/api/ingredients/similar", headers=anna.headers)
    assert fields(response) == {("query", "name"): "required"}


async def test_at_most_five_similar_ingredients(api: AsyncClient, anna: Account) -> None:
    for i in range(7):
        await create_ingredient(api, anna, f"Tee {i}")
    response = await api.get(
        "/api/ingredients/similar", params={"name": "Tee"}, headers=anna.headers
    )
    assert [item["name"] for item in response.json()] == [f"Tee {i}" for i in range(5)]


# --- editing (ING-01, ING-02) ------------------------------------------------------------------


async def test_anyone_edits_and_is_recorded(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    categories = await category_ids(api, anna)
    apples = await create_ingredient(
        api, anna, "Apfel", piece_weight_g=180, density_g_per_ml=0.8, manual={"kcal": 52}
    )
    clock.advance(minutes=5)

    response = await patch(
        api,
        ben,
        apples["id"],
        name="Äpfel",
        category_id=categories["fruit_vegetables"],
        piece_weight_g=None,
        manual={"protein": 0.3, "kcal": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Äpfel"
    assert body["category_id"] == categories["fruit_vegetables"]
    assert body["piece_weight_g"] is None
    assert body["density_g_per_ml"] == 0.8  # not sent, kept
    assert body["manual"] == NO_NUTRIENTS | {"protein": 0.3}
    assert body["created_by"] == ref(anna)
    assert body["updated_by"] == ref(ben)
    assert body["created_at"] == "2026-09-27T12:00:00Z"
    assert body["updated_at"] == "2026-09-27T12:05:00Z"
    assert (await api.get(f"/api/ingredients/{apples['id']}", headers=anna.headers)).json() == body
    cleared = (await patch(api, anna, apples["id"], density_g_per_ml=None)).json()
    assert cleared["density_g_per_ml"] is None


async def test_rename_checks_other_names(api: AsyncClient, anna: Account) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")
    await create_ingredient(api, anna, "Birnen")
    response = await patch(api, anna, apples["id"], name="birnen", category_id="nope")
    assert response.status_code == 422
    assert fields(response) == {("body", "name"): "taken", ("body", "category_id"): "invalid"}
    # Its own name in another spelling is fine.
    assert (await patch(api, anna, apples["id"], name="AEPFEL")).json()["name"] == "AEPFEL"


async def test_invalid_updates(api: AsyncClient, anna: Account) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")
    response = await patch(api, anna, apples["id"], name="", manual={"fat": 101})
    assert fields(response) == {
        ("body", "name"): "too_short",
        ("body", "manual", "fat"): "out_of_range",
    }


async def test_null_is_refused_for_required_fields(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")
    clock.advance(minutes=1)
    response = await patch(api, ben, apples["id"], name=None, category_id=None, base_unit=None)
    assert response.status_code == 422
    assert error(response) == "common.validation"
    assert fields(response) == {
        ("body", "name"): "invalid",
        ("body", "category_id"): "invalid",
        ("body", "base_unit"): "invalid",
    }
    for field in ("name", "category_id", "base_unit"):
        alone = await patch(api, ben, apples["id"], **{field: None})
        assert fields(alone) == {("body", field): "invalid"}
    unchanged = await api.get(f"/api/ingredients/{apples['id']}", headers=anna.headers)
    assert unchanged.json() == apples


async def test_base_unit_is_locked_while_products_are_linked(
    api: AsyncClient, anna: Account
) -> None:
    oil = await create_ingredient(api, anna, "Olivenöl")
    assert (await patch(api, anna, oil["id"], base_unit="ml")).json()["base_unit"] == "ml"
    await create_product(api, anna, oil["id"], EAN_13)

    response = await patch(api, anna, oil["id"], base_unit="g", name="Öl")

    assert response.status_code == 409
    assert error(response) == "ingredient.base_unit_locked"
    unchanged = (await api.get(f"/api/ingredients/{oil['id']}", headers=anna.headers)).json()
    assert (unchanged["name"], unchanged["base_unit"]) == ("Olivenöl", "ml")
    # Sending the current base unit is fine.
    assert (await patch(api, anna, oil["id"], base_unit="ml")).status_code == 200


async def test_an_empty_update_only_records_the_editor(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    apples = await create_ingredient(api, anna, "Äpfel", piece_weight_g=180)
    clock.advance(minutes=1)
    body = (await patch(api, ben, apples["id"])).json()
    changed = {"updated_by": None, "updated_at": None}
    assert body | changed == apples | changed
    assert body["updated_at"] == "2026-09-27T12:01:00Z"
    assert body["updated_by"] == ref(ben)


# --- nutrition (NUT-02) ------------------------------------------------------------------------


async def test_nutrition_sources(api: AsyncClient, anna: Account) -> None:
    pasta = await create_ingredient(api, anna, "Spaghetti", manual={"fat": 1.8})
    await create_product(api, anna, pasta["id"], EAN_13, nutrients={"kcal": 350, "fat": 2})
    await create_product(api, anna, pasta["id"], EAN_13_B, nutrients={"kcal": 360, "sugar": 3})
    await create_product(api, anna, pasta["id"], UPC_A, nutrients={"kcal": 361})

    body = (await api.get(f"/api/ingredients/{pasta['id']}", headers=anna.headers)).json()

    assert body["product_count"] == 3
    nutrition = body["nutrition"]
    assert nutrition["kcal"]["source"] == "products"
    assert nutrition["kcal"]["value"] == pytest.approx(357)
    assert nutrition["kcal"]["products_mean"] == pytest.approx(357)
    assert nutrition["kcal"]["products_count"] == 3
    assert nutrition["sugar"] == {
        "value": 3,
        "source": "products",
        "products_mean": 3,
        "products_count": 1,
    }
    assert nutrition["fat"] == {
        "value": 1.8,
        "source": "manual",
        "products_mean": 2,
        "products_count": 1,
    }
    assert nutrition["protein"] == unknown_nutrition()["protein"]


async def test_deleted_creator(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, admin: Account
) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")
    await patch(api, ben, apples["id"], piece_weight_g=180)
    assert (
        await api.delete(f"/api/admin/users/{anna.id}", headers=admin.headers)
    ).status_code == 204

    body = (await api.get(f"/api/ingredients/{apples['id']}", headers=ben.headers)).json()

    assert body["created_by"] is None
    assert body["updated_by"] == ref(ben)
    assert await scalars(app, select(Ingredient.name)) == ["Äpfel"]


async def test_products_of_an_ingredient(api: AsyncClient, anna: Account) -> None:
    pasta = await create_ingredient(api, anna, "Spaghetti")
    other = await create_ingredient(api, anna, "Reis")
    await create_product(api, anna, pasta["id"], EAN_13)
    await create_product(api, anna, pasta["id"], EAN_8, name="spaghetti n.5")
    await create_product(api, anna, pasta["id"], UPC_A, name="Bio-Spaghetti")
    await create_product(api, anna, other["id"], EAN_13_B)
    assert (await api.get(f"/api/ingredients/{other['id']}/products", headers=anna.headers)).json()[
        0
    ]["barcode"] == EAN_13_B

    response = await api.get(f"/api/ingredients/{pasta['id']}/products", headers=anna.headers)

    assert response.status_code == 200
    assert [(item["name"], item["barcode"]) for item in response.json()] == [
        ("Bio-Spaghetti", f"0{UPC_A}"),
        ("spaghetti n.5", EAN_8),
        (None, EAN_13),
    ]


# --- merge and delete (ING-05, admins) ---------------------------------------------------------


async def merge(api: AsyncClient, user: Account, ingredient_id: str, into_id: str) -> Any:
    return await api.post(
        f"/api/admin/ingredients/{ingredient_id}/merge",
        json={"into_id": into_id},
        headers=user.headers,
    )


async def events(api: AsyncClient, admin: Account) -> list[tuple[str, dict[str, Any]]]:
    response = await api.get("/api/admin/events", headers=admin.headers)
    return [(event["action"], event["details"]) for event in response.json()]


async def test_merge(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    admin: Account,
    monkeypatch: pytest.MonkeyPatch,
    clock: FakeClock,
) -> None:
    calls: list[tuple[str, str]] = []

    async def on_ingredients_merged(_session: object, from_id: str, into_id: str) -> None:
        calls.append((from_id, into_id))

    monkeypatch.setattr(hooks, "on_ingredients_merged", on_ingredients_merged)
    duplicate = await create_ingredient(api, anna, "Paradeiser", manual={"kcal": 20})
    tomatoes = await create_ingredient(api, anna, "Tomaten", piece_weight_g=100)
    await create_product(api, anna, duplicate["id"], EAN_13, nutrients={"kcal": 18})
    await create_product(api, anna, tomatoes["id"], EAN_8, nutrients={"kcal": 22})
    clock.advance(minutes=10)

    response = await merge(api, admin, duplicate["id"], tomatoes["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == tomatoes["id"]
    assert body["name"] == "Tomaten"
    assert body["piece_weight_g"] == 100
    assert body["product_count"] == 2
    assert body["nutrition"]["kcal"]["value"] == pytest.approx(20)
    assert body["manual"] == NO_NUTRIENTS
    # The target and the moved products were last changed by the admin; the others were not.
    assert (body["created_by"], body["updated_by"]) == (ref(anna), ref(admin))
    assert body["updated_at"] == "2026-09-27T12:10:00Z"
    linked = await api.get(f"/api/ingredients/{tomatoes['id']}/products", headers=anna.headers)
    assert {
        item["barcode"]: (item["updated_by"], item["updated_at"]) for item in linked.json()
    } == {
        EAN_13: (ref(admin), "2026-09-27T12:10:00Z"),
        EAN_8: (ref(anna), "2026-09-27T12:00:00Z"),
    }
    assert calls == [(duplicate["id"], tomatoes["id"])]
    assert await scalars(app, select(Ingredient.name)) == ["Tomaten"]
    assert set(await scalars(app, select(Product.ingredient_id))) == {tomatoes["id"]}
    missing = await api.get(f"/api/ingredients/{duplicate['id']}", headers=anna.headers)
    assert missing.status_code == 404
    assert await events(api, admin) == [
        ("ingredient.merge", {"from_name": "Paradeiser", "into_name": "Tomaten"})
    ]


async def test_merge_with_different_base_units(
    api: AsyncClient, anna: Account, admin: Account
) -> None:
    cream = await create_ingredient(api, anna, "Sahne", base_unit="ml")
    cream_g = await create_ingredient(api, anna, "Schlagsahne")
    empty = await create_ingredient(api, anna, "Rahm", base_unit="ml")
    await create_product(api, anna, cream["id"], EAN_13)

    response = await merge(api, admin, cream["id"], cream_g["id"])
    assert response.status_code == 409
    assert error(response) == "ingredient.merge_base_unit_mismatch"
    # Without products, the base unit does not matter.
    assert (await merge(api, admin, empty["id"], cream_g["id"])).status_code == 200


async def test_invalid_merges(api: AsyncClient, anna: Account, admin: Account) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")

    itself = await merge(api, admin, apples["id"], apples["id"])
    assert fields(itself) == {("body", "into_id"): "invalid"}
    unknown_target = await merge(api, admin, apples["id"], "nope")
    assert fields(unknown_target) == {("body", "into_id"): "invalid"}
    unknown_source = await merge(api, admin, "nope", apples["id"])
    assert unknown_source.status_code == 404
    assert error(unknown_source) == "common.not_found"
    missing = await api.post(
        f"/api/admin/ingredients/{apples['id']}/merge", json={}, headers=admin.headers
    )
    assert fields(missing) == {("body", "into_id"): "required"}


async def test_delete(app: FastAPI, api: AsyncClient, anna: Account, admin: Account) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")

    response = await api.delete(f"/api/admin/ingredients/{apples['id']}", headers=admin.headers)

    assert response.status_code == 204
    assert await scalars(app, select(Ingredient.id)) == []
    assert await events(api, admin) == [("ingredient.delete", {"name": "Äpfel"})]
    again = await api.delete(f"/api/admin/ingredients/{apples['id']}", headers=admin.headers)
    assert again.status_code == 404


async def test_ingredients_in_use_are_not_deleted(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    admin: Account,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pasta = await create_ingredient(api, anna, "Spaghetti")
    rice = await create_ingredient(api, anna, "Reis")
    await create_product(api, anna, pasta["id"], EAN_13)
    await create_product(api, anna, pasta["id"], EAN_8)

    response = await api.delete(f"/api/admin/ingredients/{pasta['id']}", headers=admin.headers)
    assert response.status_code == 409
    assert error(response) == "ingredient.in_use"
    assert response.json()["params"] == {"products": 2}

    async def ingredient_references(_session: object, ingredient_id: str) -> dict[str, int]:
        return {"meals": 3} if ingredient_id == rice["id"] else {}

    monkeypatch.setattr(hooks, "ingredient_references", ingredient_references)
    response = await api.delete(f"/api/admin/ingredients/{rice['id']}", headers=admin.headers)
    assert response.status_code == 409
    assert response.json()["params"] == {"products": 0, "meals": 3}
    assert len(await scalars(app, select(Ingredient.id))) == 2
    assert await scalars(app, select(AdminEvent.id)) == []


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [("POST", "/merge", {"into_id": "x"}), ("DELETE", "", None)],
)
async def test_only_admins_merge_and_delete(
    app: FastAPI, api: AsyncClient, anna: Account, method: str, suffix: str, body: Any
) -> None:
    apples = await create_ingredient(api, anna, "Äpfel")
    pears = await create_ingredient(api, anna, "Birnen")
    if body is not None:
        body = {"into_id": pears["id"]}
    response = await api.request(
        method, f"/api/admin/ingredients/{apples['id']}{suffix}", json=body, headers=anna.headers
    )
    assert response.status_code == 403
    assert error(response) == "common.forbidden"
    assert len(await scalars(app, select(Ingredient.id))) == 2
