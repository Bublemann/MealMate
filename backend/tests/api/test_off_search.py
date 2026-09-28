"""Finding products on Open Food Facts by name (BAR-08, owner decision 2026-09-28): the query
rules, the proposals, "already in MealMate", its own rate limit, the cache."""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.ratelimit import SlidingWindow
from app.services.off_search import SearchAnswer, SearchCache
from tests.accounts import Account, FakeClock, error, fields, make_user
from tests.catalog import create_ingredient
from tests.off import (
    MILK,
    OATS,
    OFF_URL,
    oats,
    product_response,
    refresher,
    search_response,
    search_route,
)

OATS_PRODUCT = oats()["product"]
MILK_PRODUCT = product_response(
    MILK,
    product_name_de="Frische Vollmilch",
    brands="Weihenstephan",
    quantity="1 l",
    product_quantity=1000,
    product_quantity_unit="ml",
    nutrition_data_per="100g",
    nutriments={"energy-kcal_100g": 64},
)["product"]


@pytest.fixture
def off_api(app: FastAPI) -> Iterator[respx.MockRouter]:
    app.state.off_refresh = refresher()
    with respx.mock(base_url=OFF_URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben", language="en")


async def search(api: AsyncClient, user: Account, q: str, **params: Any) -> httpx.Response:
    return await api.get(
        "/api/ingredients/off-search", params={"q": q, **params}, headers=user.headers
    )


@pytest.mark.parametrize(
    ("params", "loc", "code"),
    [
        ({"q": "a"}, ("query", "q"), "too_short"),
        ({"q": "  a   "}, ("query", "q"), "too_short"),
        ({"q": "x" * 81}, ("query", "q"), "too_long"),
        ({}, ("query", "q"), "required"),
        ({"q": "milch", "page": 0}, ("query", "page"), "out_of_range"),
        ({"q": "milch", "page": 51}, ("query", "page"), "out_of_range"),
    ],
)
async def test_the_query_is_checked_first(
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    params: dict[str, Any],
    loc: tuple[str, ...],
    code: str,
) -> None:
    response = await api.get("/api/ingredients/off-search", params=params, headers=anna.headers)
    assert response.status_code == 422
    assert fields(response) == {loc: code}
    assert not off_api.calls


async def test_results_are_proposals_like_a_scan(
    api: AsyncClient, anna: Account, off_api: respx.MockRouter
) -> None:
    request = search_route(off_api).respond(
        json=search_response(OATS_PRODUCT, MILK_PRODUCT, count=2)
    )

    response = await search(api, anna, "  Hafer  ")

    assert response.status_code == 200
    assert request.calls.last.request.url.params["search_terms"] == "Hafer"
    assert request.calls.last.request.url.params["lc"] == "de"
    assert response.json() == {
        "q": "Hafer",
        "page": 1,
        "results": [
            {
                "proposal": {
                    "barcode": OATS,
                    "name": "Haferflocken",
                    "brand": "MealMate Test Kitchen",
                    "quantity_text": "500 g",
                    "pack_quantity": 500,
                    "pack_unit": "g",
                    "nutrition_basis": "g",
                    "nutrients": {
                        "kcal": 372,
                        "protein": 13.5,
                        "carbs": 58.7,
                        "sugar": 0.7,
                        "fat": 7,
                    },
                    "category_key": "breakfast_spreads",
                    "off_last_modified_at": "2026-01-01T00:00:00Z",
                },
                "in_mealmate": False,
                "ingredient": None,
            },
            {
                "proposal": {
                    "barcode": MILK,
                    "name": "Frische Vollmilch",
                    "brand": "Weihenstephan",
                    "quantity_text": "1 l",
                    "pack_quantity": 1000,
                    "pack_unit": "ml",
                    "nutrition_basis": "ml",
                    "nutrients": {
                        "kcal": 64,
                        "protein": None,
                        "carbs": None,
                        "sugar": None,
                        "fat": None,
                    },
                    "category_key": None,
                    "off_last_modified_at": None,
                },
                "in_mealmate": False,
                "ingredient": None,
            },
        ],
        "has_more": False,
    }


async def test_names_follow_the_users_language(
    api: AsyncClient, ben: Account, off_api: respx.MockRouter
) -> None:
    request = search_route(off_api).respond(json=search_response(OATS_PRODUCT))
    body = (await search(api, ben, "oats")).json()
    assert body["results"][0]["proposal"]["name"] == "Rolled Oats"
    assert request.calls.last.request.url.params["lc"] == "en"


async def test_products_are_cleaned_and_those_without_a_barcode_left_out(
    api: AsyncClient, anna: Account, off_api: respx.MockRouter
) -> None:
    hostile = {
        "code": OATS,
        "product_name": "‮Snack\x00 with\x07 hidden characters",
        "brands": "Evil Corp " + "X" * 200,
        "nutrition_data_per": "100g",
        "nutriments": {"energy-kcal_100g": 99999, "proteins_100g": -5},
    }
    no_barcode = OATS_PRODUCT | {"code": "123"}
    duplicate = OATS_PRODUCT | {"product_name_de": "Doppelt"}
    search_route(off_api).respond(json=search_response(hostile, no_barcode, duplicate))

    [result] = (await search(api, anna, "snack")).json()["results"]

    proposal = result["proposal"]
    assert (proposal["barcode"], proposal["name"]) == (OATS, "Snack with hidden characters")
    assert proposal["brand"] == "Evil Corp " + "X" * 70
    assert (proposal["nutrients"]["kcal"], proposal["nutrients"]["protein"]) == (None, None)


async def test_products_already_in_mealmate_are_flagged(
    api: AsyncClient, anna: Account, off_api: respx.MockRouter
) -> None:
    known = await create_ingredient(api, anna, "Milch", brand="Weihenstephan", barcode=MILK)
    search_route(off_api).respond(json=search_response(OATS_PRODUCT, MILK_PRODUCT))

    results = (await search(api, anna, "milch")).json()["results"]

    assert [(item["in_mealmate"], item["ingredient"]) for item in results] == [
        (False, None),
        (
            True,
            {
                "id": known["id"],
                "name": "Milch",
                "brand": "Weihenstephan",
                "barcode": MILK,
                "source": "manual",
                "category_id": known["category_id"],
                "base_unit": "g",
            },
        ),
    ]


async def test_more_pages(api: AsyncClient, anna: Account, off_api: respx.MockRouter) -> None:
    request = search_route(off_api).respond(json=search_response(OATS_PRODUCT, count=41))

    first = (await search(api, anna, "hafer")).json()
    third = (await search(api, anna, "hafer", page=3)).json()
    last = (await search(api, anna, "hafer", page=50)).json()

    assert (first["page"], first["has_more"]) == (1, True)
    assert (third["page"], third["has_more"]) == (3, False)
    assert [call.request.url.params["page"] for call in request.calls] == ["1", "3", "50"]
    request.respond(json=search_response(OATS_PRODUCT, count=10_000))
    assert (await search(api, anna, "hafer", page=49)).json()["has_more"] is True
    assert last["has_more"] is False  # no page after the last one allowed


async def test_repeated_searches_come_from_the_cache(
    api: AsyncClient, anna: Account, ben: Account, off_api: respx.MockRouter
) -> None:
    """Per normalised query, page and name language, for 24 hours: repeating a search does
    not ask Open Food Facts again (BAR-08)."""
    request = search_route(off_api).respond(json=search_response(OATS_PRODUCT))

    first = (await search(api, anna, "Haferflocken")).json()
    assert (await search(api, anna, " HAFERFLOCKEN ")).json()["results"] == first["results"]
    assert request.call_count == 1
    await search(api, anna, "Haferflocken", page=2)
    await search(api, ben, "Haferflocken")  # names in another language
    assert request.call_count == 3


async def test_a_known_product_is_flagged_also_from_the_cache(
    api: AsyncClient, anna: Account, off_api: respx.MockRouter
) -> None:
    search_route(off_api).respond(json=search_response(OATS_PRODUCT))
    assert (await search(api, anna, "hafer")).json()["results"][0]["in_mealmate"] is False
    await create_ingredient(api, anna, "Haferflocken", barcode=OATS)
    assert (await search(api, anna, "hafer")).json()["results"][0]["in_mealmate"] is True


async def test_busy_while_too_many_searches_wait(
    app: FastAPI, api: AsyncClient, anna: Account, off_api: respx.MockRouter, clock: FakeClock
) -> None:
    """Searches have a rate limit of their own; a busy one is not cached."""
    app.state.off_refresh = refresher(search_rate_limit=SlidingWindow(1, clock=clock.monotonic))
    request = search_route(off_api).respond(json=search_response(OATS_PRODUCT))
    assert (await search(api, anna, "hafer")).status_code == 200

    response = await search(api, anna, "milch")

    assert response.status_code == 503
    assert error(response) == "off.busy"
    assert request.call_count == 1
    assert (await search(api, anna, "hafer")).status_code == 200  # cached: no request


@pytest.mark.parametrize(
    "answer", [httpx.Response(502), httpx.Response(200, text="{"), httpx.ConnectTimeout("slow")]
)
async def test_unavailable(
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    answer: httpx.Response | Exception,
) -> None:
    """Slow or unreachable: 503 `off.unavailable` ("Open Food Facts is slow, try again"),
    and nothing is cached, so trying again asks again."""
    if isinstance(answer, Exception):
        request = search_route(off_api).mock(side_effect=answer)
    else:
        request = search_route(off_api).mock(return_value=answer)

    response = await search(api, anna, "hafer")

    assert response.status_code == 503
    assert error(response) == "off.unavailable"
    calls = request.call_count
    request.mock(side_effect=None, return_value=httpx.Response(200, json=search_response()))
    assert (await search(api, anna, "hafer")).json()["results"] == []
    assert request.call_count == calls + 1


# --- the cache -------------------------------------------------------------------------------


def test_cache_entries_expire_after_a_day() -> None:
    now = [0.0]
    cache = SearchCache(clock=lambda: now[0])
    answer = SearchAnswer((), 0)
    cache.put(("milch", 1, "de"), answer)
    now[0] = 24 * 60 * 60 - 1
    assert cache.get(("milch", 1, "de")) is answer
    now[0] = 24 * 60 * 60
    assert cache.get(("milch", 1, "de")) is None
    assert len(cache) == 0
    assert cache.get(("milch", 1, "de")) is None


def test_the_least_recently_used_entry_goes_first() -> None:
    cache = SearchCache(max_entries=2)
    answers = [SearchAnswer((), count) for count in range(3)]
    cache.put(("a", 1, "de"), answers[0])
    cache.put(("b", 1, "de"), answers[1])
    assert cache.get(("a", 1, "de")) is answers[0]  # now b is the least recently used
    cache.put(("c", 1, "de"), answers[2])
    assert len(cache) == 2
    assert cache.get(("b", 1, "de")) is None
    assert cache.get(("a", 1, "de")) is answers[0]
    assert cache.get(("c", 1, "de")) is answers[2]
