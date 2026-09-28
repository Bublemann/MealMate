"""The barcode lookup and saving an Open Food Facts proposal (BAR-02, BAR-03, BAR-04, BAR-08)."""

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.core.ratelimit import SlidingWindow
from app.models import Product as ProductRow
from tests.accounts import Account, FakeClock, error, fields, make_user, scalars
from tests.catalog import EAN_13, NO_NUTRIENTS, UPC_A, create_ingredient, create_product, ref
from tests.off import (
    MILK,
    OATS,
    OFF_URL,
    RECORDED_BARCODE,
    UNKNOWN,
    oats,
    product_response,
    recorded,
    refresher,
    route,
)
from tests.support import serve

OATS_NUTRIENTS = {"kcal": 372, "protein": 13.5, "carbs": 58.7, "sugar": 0.7, "fat": 7}


@pytest.fixture
def off_api(app: FastAPI) -> Iterator[respx.MockRouter]:
    """Open Food Facts at OFF_URL, mocked; routes that are not set up fail the test."""
    app.state.off_refresh = refresher()
    with respx.mock(base_url=OFF_URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben", language="en")


async def lookup(api: AsyncClient, user: Account, barcode: str) -> httpx.Response:
    return await api.get("/api/products/lookup", params={"barcode": barcode}, headers=user.headers)


# --- lookup (BAR-02, BAR-03) ----------------------------------------------------------------------


async def test_lookup_needs_a_login(api: AsyncClient, off_api: respx.MockRouter) -> None:
    response = await api.get("/api/products/lookup", params={"barcode": OATS})
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("params", "problem"),
    [
        ({"barcode": "4006381333932"}, "invalid_format"),
        ({"barcode": "not a barcode"}, "invalid_format"),
        ({"barcode": ""}, "invalid_format"),
        ({"barcode": "1" * 33}, "too_long"),
        ({}, "required"),
    ],
)
async def test_lookup_rejects_invalid_barcodes(
    api: AsyncClient, anna: Account, off_api: respx.MockRouter, params: Any, problem: str
) -> None:
    response = await api.get("/api/products/lookup", params=params, headers=anna.headers)

    assert response.status_code == 422
    assert fields(response) == {("query", "barcode"): problem}
    assert not off_api.calls


async def test_a_known_barcode_goes_straight_to_its_ingredient(
    api: AsyncClient, anna: Account, off_api: respx.MockRouter
) -> None:
    oats_ingredient = await create_ingredient(api, anna, "Haferflocken")
    product = await create_product(api, anna, oats_ingredient["id"], UPC_A, name="Kernige")

    response = await lookup(api, anna, f"0{UPC_A}")

    assert response.status_code == 200
    assert response.json() == {
        "barcode": f"0{UPC_A}",
        "found_in": "db",
        "product": product,
        "ingredient": {
            "id": oats_ingredient["id"],
            "name": "Haferflocken",
            "category_id": oats_ingredient["category_id"],
            "base_unit": "g",
            "product_count": 1,
        },
        "proposal": None,
        "suggestions": [],
        "off_unavailable": False,
    }
    assert not off_api.calls  # our own database first; a manual product is never refreshed


async def test_an_open_food_facts_proposal_is_not_saved(
    app: FastAPI, api: AsyncClient, anna: Account, off_api: respx.MockRouter
) -> None:
    await create_ingredient(api, anna, "Haferflocken")
    await create_ingredient(api, anna, "Hafer")
    await create_ingredient(api, anna, "Milch")
    route(off_api, OATS).respond(json=oats())

    response = await lookup(api, anna, OATS)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "barcode": OATS,
        "found_in": "off",
        "product": None,
        "ingredient": None,
        "proposal": {
            "name": "Haferflocken",
            "brand": "MealMate Test Kitchen",
            "quantity_text": "500 g",
            "pack_quantity": 500,
            "pack_unit": "g",
            "nutrition_basis": "g",
            "nutrients": OATS_NUTRIENTS,
            "category_key": "breakfast_spreads",
            "off_last_modified_at": "2026-01-01T00:00:00Z",
        },
        "suggestions": body["suggestions"],
        "off_unavailable": False,
    }
    # "Which ingredient is this?": name-matched candidates, the exact match first.
    assert [item["name"] for item in body["suggestions"]] == ["Haferflocken", "Hafer"]
    assert await scalars(app, select(ProductRow.id)) == []


async def test_the_proposal_name_follows_the_users_language(
    api: AsyncClient, ben: Account, off_api: respx.MockRouter
) -> None:
    route(off_api, OATS).respond(json=oats())
    route(off_api, RECORDED_BARCODE).respond(json=recorded("product_found"))

    assert (await lookup(api, ben, OATS)).json()["proposal"]["name"] == "Rolled Oats"
    recorded_proposal = (await lookup(api, ben, RECORDED_BARCODE)).json()["proposal"]
    assert recorded_proposal == {
        "name": "test_default",
        "brand": None,
        "quantity_text": "100 g",
        "pack_quantity": 100,
        "pack_unit": "g",
        "nutrition_basis": "g",
        "nutrients": {"kcal": 140.5, "protein": 4.5, "carbs": 10.5, "sugar": 12.5, "fat": 8.5},
        "category_key": "snacks_sweets",
        "off_last_modified_at": "2026-01-01T00:00:00Z",
    }


async def test_a_proposal_without_basis_or_name(
    api: AsyncClient, anna: Account, off_api: respx.MockRouter
) -> None:
    await create_ingredient(api, anna, "Milch", base_unit="ml")
    route(off_api, MILK).respond(
        json=product_response(
            MILK,
            nutrition_data_per="serving",
            nutriments={"energy-kcal_100g": 64},
            product_quantity="1000",
            product_quantity_unit="ml",
        )
    )

    body = (await lookup(api, anna, MILK)).json()

    assert body["found_in"] == "off"
    proposal = body["proposal"]
    assert (proposal["name"], proposal["nutrition_basis"]) == (None, None)
    assert proposal["nutrients"] == NO_NUTRIENTS
    assert (proposal["pack_quantity"], proposal["pack_unit"]) == (1000, "ml")
    assert body["suggestions"] == []


async def test_a_hostile_product_is_cleaned(
    api: AsyncClient, ben: Account, off_api: respx.MockRouter
) -> None:
    route(off_api, OATS).respond(
        json=product_response(
            OATS,
            product_name="‮Snack\x00 with\x07 ​hidden⁦ characters\n\t",
            brands="Evil Corp " + "X" * 200,
            nutrition_data_per="100g",
            nutriments={"energy-kcal_100g": 99999, "proteins_100g": -5, "fat_100g": "NaN"},
            last_modified_t="yesterday",
        )
    )

    proposal = (await lookup(api, ben, OATS)).json()["proposal"]

    assert proposal["name"] == "Snack with hidden characters"
    assert proposal["brand"] == "Evil Corp " + "X" * 70
    assert proposal["nutrients"] == NO_NUTRIENTS
    assert proposal["off_last_modified_at"] is None


async def test_lone_surrogates_are_removed(
    api: AsyncClient, ben: Account, off_api: respx.MockRouter
) -> None:
    """Half a UTF-16 pair (`\\ud800` in JSON) cannot be encoded; it is dropped like a control
    character, and so are private-use and unassigned ones."""
    answer = product_response(OATS, product_name="Oat\ud800s\ue000", brands="Test\udfff\u0378")
    route(off_api, OATS).respond(
        content=json.dumps(answer).encode(), headers={"Content-Type": "application/json"}
    )

    response = await lookup(api, ben, OATS)

    assert response.status_code == 200
    proposal = response.json()["proposal"]
    assert (proposal["name"], proposal["brand"]) == ("Oats", "Test")


@pytest.mark.parametrize(
    ("answer", "unavailable"),
    [
        (httpx.Response(404, json=recorded("product_not_found")), False),
        (httpx.Response(200, json=recorded("product_not_found")), False),
        (httpx.Response(502), True),
        (httpx.Response(200, text="{"), True),
        (httpx.ConnectTimeout("slow"), True),
    ],
)
async def test_nothing_found(
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    answer: httpx.Response | Exception,
    unavailable: bool,
) -> None:
    """Not found (enter the values yourself), or Open Food Facts is slow or unreachable."""
    if isinstance(answer, Exception):
        route(off_api, UNKNOWN).mock(side_effect=answer)
    else:
        route(off_api, UNKNOWN).mock(return_value=answer)

    response = await lookup(api, anna, UNKNOWN)

    assert response.status_code == 200
    assert response.json() == {
        "barcode": UNKNOWN,
        "found_in": "none",
        "product": None,
        "ingredient": None,
        "proposal": None,
        "suggestions": [],
        "off_unavailable": unavailable,
    }


async def test_busy_while_too_many_lookups_wait(
    app: FastAPI, api: AsyncClient, anna: Account, off_api: respx.MockRouter, clock: FakeClock
) -> None:
    """At most N requests start in any minute; a lookup waits at most 5 s for its turn
    (BAR-08)."""
    app.state.off_refresh = refresher(SlidingWindow(2, clock=clock.monotonic))
    request = route(off_api, UNKNOWN).respond(404, json=recorded("product_not_found"))
    for _ in range(2):
        assert (await lookup(api, anna, UNKNOWN)).status_code == 200

    response = await lookup(api, anna, UNKNOWN)

    assert response.status_code == 503
    assert error(response) == "off.busy"
    assert request.call_count == 2
    clock.advance(seconds=55.5)  # the next start is now 4.5 s away: worth the wait
    app.state.off_refresh.off.rate_limit.sleep = _no_sleep
    assert (await lookup(api, anna, UNKNOWN)).status_code == 200


async def test_unknown_products_do_not_use_up_the_lookups(
    app: FastAPI, api: AsyncClient, anna: Account, off_api: respx.MockRouter, clock: FakeClock
) -> None:
    """Open Food Facts' "not found" is final: it is not asked again, so each scan of an unknown
    product takes one of the app's places per minute, and as many unknown scans as there are
    places are all answered, none of them `busy`."""
    per_minute = app.state.settings.off_rate_app_per_minute
    app.state.off_refresh = refresher(SlidingWindow(per_minute, clock=clock.monotonic))
    request = route(off_api, UNKNOWN).respond(404, json=recorded("product_not_found"))

    for _ in range(per_minute):
        response = await lookup(api, anna, UNKNOWN)
        assert response.status_code == 200
        assert (response.json()["found_in"], response.json()["off_unavailable"]) == (
            "none",
            False,
        )

    assert request.call_count == per_minute


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(503),
        httpx.Response(404, text="<html>Not Found</html>"),  # an error page in front of OFF
        httpx.ConnectError("refused"),
    ],
)
async def test_a_lookup_asks_open_food_facts_again_after_a_transient_failure(
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    failure: httpx.Response | Exception,
) -> None:
    """The first scan of a product must not end in "Open Food Facts is slow" when a second
    request, a moment later, finds it."""
    request = route(off_api, OATS).mock(side_effect=[failure, httpx.Response(200, json=oats())])

    body = (await lookup(api, anna, OATS)).json()

    assert (body["found_in"], body["proposal"]["name"]) == ("off", "Haferflocken")
    assert request.call_count == 2


async def test_the_lifespan_closes_the_open_food_facts_connections(
    app: FastAPI, off_api: respx.MockRouter
) -> None:
    route(off_api, OATS).respond(json=oats())
    off = app.state.off_refresh.off

    async with serve(app):
        assert (await off.fetch(OATS, max_wait=None)).status == "found"
        assert off.is_open

    assert not off.is_open


async def _no_sleep(_seconds: float) -> None:
    return None


# --- saving (ING-04, BAR-04) ----------------------------------------------------------------------


async def test_save_a_proposal_marks_only_the_changed_fields(
    app: FastAPI, api: AsyncClient, anna: Account, off_api: respx.MockRouter
) -> None:
    ingredient = await create_ingredient(api, anna, "Haferflocken")

    response = await api.post(
        "/api/products",
        json={
            "barcode": OATS,
            "ingredient_id": ingredient["id"],
            "source": "off",
            "off_last_modified_at": "2026-01-01T00:00:00Z",
            "edited_fields": ["nutrients.kcal", "name", "name"],
            "name": "Zarte Haferflocken",
            "brand": "MealMate Test Kitchen",
            "quantity_text": "500 g",
            "pack_quantity": 500,
            "pack_unit": "g",
            "nutrients": OATS_NUTRIENTS | {"kcal": 370},
        },
        headers=anna.headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "barcode": OATS,
        "ingredient_id": ingredient["id"],
        "nutrition_basis": "g",
        "name": "Zarte Haferflocken",
        "brand": "MealMate Test Kitchen",
        "quantity_text": "500 g",
        "pack_quantity": 500,
        "pack_unit": "g",
        "nutrients": OATS_NUTRIENTS | {"kcal": 370},
        "source": "off",
        "user_edited_fields": ["name", "nutrients.kcal"],
        "fetched_at": "2026-09-27T12:00:00Z",
        "pending_update": None,
        "created_by": ref(anna),
        "updated_by": ref(anna),
        "created_at": "2026-09-27T12:00:00Z",
        "updated_at": "2026-09-27T12:00:00Z",
    }
    [modified_at] = await scalars(app, select(ProductRow.off_last_modified_at))
    assert modified_at.isoformat() == "2026-01-01T00:00:00+00:00"
    # Found in our own database from now on (BAR-02).
    assert (await lookup(api, anna, OATS)).json()["found_in"] == "db"
    assert not off_api.calls


async def test_save_a_proposal_without_edits(app: FastAPI, api: AsyncClient, anna: Account) -> None:
    ingredient = await create_ingredient(api, anna, "Haferflocken")

    body = await create_product(
        api, anna, ingredient["id"], OATS, source="off", name="Haferflocken", nutrients={}
    )

    assert (body["source"], body["user_edited_fields"]) == ("off", [])
    assert await scalars(app, select(ProductRow.off_last_modified_at)) == [None]


async def test_manual_products_ignore_the_open_food_facts_fields(
    app: FastAPI, api: AsyncClient, anna: Account
) -> None:
    ingredient = await create_ingredient(api, anna, "Haferflocken")

    body = await create_product(
        api,
        anna,
        ingredient["id"],
        EAN_13,
        name="Haferflocken",
        off_last_modified_at="2026-01-01T00:00:00Z",
        edited_fields=["brand"],
    )

    assert (body["source"], body["fetched_at"]) == ("manual", None)
    assert body["user_edited_fields"] == ["name"]
    assert await scalars(app, select(ProductRow.off_last_modified_at)) == [None]


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"edited_fields": ["barcode"]}, ("body", "edited_fields", 0)),
        ({"edited_fields": ["nutrients.salt"]}, ("body", "edited_fields", 0)),
        ({"edited_fields": ["name"] * 12}, ("body", "edited_fields")),
        ({"off_last_modified_at": "2026-01-01T00:00:00"}, ("body", "off_last_modified_at")),
        ({"source": "import"}, ("body", "source")),
    ],
)
async def test_save_rejects_invalid_open_food_facts_fields(
    api: AsyncClient, anna: Account, changes: dict[str, Any], problem: tuple[str | int, ...]
) -> None:
    ingredient = await create_ingredient(api, anna, "Haferflocken")

    response = await api.post(
        "/api/products",
        json={"barcode": OATS, "ingredient_id": ingredient["id"], "source": "off", **changes},
        headers=anna.headers,
    )

    assert response.status_code == 422
    assert list(fields(response)) == [problem]


async def test_save_a_proposal_checks_the_basis(api: AsyncClient, anna: Account) -> None:
    milk = await create_ingredient(api, anna, "Milch", base_unit="ml")

    response = await api.post(
        "/api/products",
        json={
            "barcode": MILK,
            "ingredient_id": milk["id"],
            "source": "off",
            "nutrition_basis": "g",
        },
        headers=anna.headers,
    )

    assert response.status_code == 409
    assert error(response) == "product.basis_mismatch"
