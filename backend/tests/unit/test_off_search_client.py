"""The Open Food Facts name search in the client (BAR-08, BAR-10): what it asks for, how it
reads the answer, and its own rate limit."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx

from app.core.ratelimit import SlidingWindow
from app.integrations.off import FIELDS, OffClient
from tests.off import (
    OATS,
    OFF_URL,
    RECORDED_BARCODE,
    client,
    oats,
    product_response,
    recorded,
    route,
    search_response,
    search_route,
)


@pytest.fixture
def off_api() -> AsyncIterator[respx.MockRouter]:
    with respx.mock(base_url=OFF_URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
async def off() -> AsyncIterator[OffClient]:
    made = client()
    yield made
    await made.aclose()


async def test_the_search_asks_for_products_sold_in_germany(
    off_api: respx.MockRouter, off: OffClient
) -> None:
    request = search_route(off_api).respond(json=search_response(oats()["product"], count=42))

    response = await off.search("Haferflocken kernig", page=2, language="en", max_wait=None)

    assert response.status == "found"
    assert response.count == 42
    [product] = response.results
    assert (product.code, product.name("en")) == (OATS, "Rolled Oats")
    params = dict(request.calls.last.request.url.params)
    assert params == {
        "search_terms": "Haferflocken kernig",
        "search_simple": "1",
        "action": "process",
        "json": "1",
        "page": "2",
        "page_size": "20",
        "sort_by": "unique_scans_n",
        "tagtype_0": "countries",
        "tag_contains_0": "contains",
        "tag_0": "en:germany",
        "lc": "en",
        "fields": FIELDS,
    }
    headers = request.calls.last.request.headers
    assert headers["user-agent"].startswith("MealMate/")
    assert headers["accept-encoding"] == "identity"


async def test_every_product_is_validated(off_api: respx.MockRouter, off: OffClient) -> None:
    """Search results are as untrusted as a looked-up product (BAR-10); entries that are no
    product object are skipped, a missing or broken count is the page's size."""
    hostile = {
        "code": "4006381333932",  # a wrong check digit: no barcode
        "product_name": "‮Snack\x00",
        "nutrition_data_per": "100g",
        "nutriments": {"energy-kcal_100g": 99999},
    }
    answer = {"products": [hostile, "not a product", 42, recorded("product_found")["product"]]}
    search_route(off_api).respond(json=answer)

    response = await off.search("snack", page=1, language="de", max_wait=None)

    assert response.status == "found"
    assert response.count == 2
    first, second = response.results
    assert (first.code, first.name("de"), first.nutrients["kcal"]) == (None, "Snack", None)
    assert second.code == RECORDED_BARCODE


async def test_an_empty_page(off_api: respx.MockRouter, off: OffClient) -> None:
    search_route(off_api).respond(json={"count": "0", "products": []})
    response = await off.search("zzzz", page=1, language="de", max_wait=None)
    assert (response.status, response.results, response.count) == ("found", (), 0)


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(200, text="{"),
        httpx.Response(200, json=["no", "object"]),
        httpx.Response(200, json={"count": 1}),
        httpx.Response(200, json={"products": {"not": "a list"}}),
        httpx.Response(302, headers={"location": "https://elsewhere.example/"}),
        httpx.Response(429),
        httpx.Response(200, json=product_response(OATS)),  # a product read, not a search page
    ],
)
async def test_unexpected_answers_are_unavailable(
    off_api: respx.MockRouter, off: OffClient, answer: httpx.Response
) -> None:
    request = search_route(off_api).mock(return_value=answer)
    response = await off.search("hafer", page=1, language="de", max_wait=None)
    assert response.status == "unavailable"
    assert request.call_count == 1  # none of these would come out differently a moment later


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(503),
        httpx.Response(404, text="<html>Not Found</html>"),  # an error page in front of OFF
        httpx.ConnectError("refused"),
    ],
)
async def test_a_transient_failure_gets_a_second_try(
    off_api: respx.MockRouter, off: OffClient, failure: httpx.Response | Exception
) -> None:
    request = search_route(off_api).mock(
        side_effect=[failure, httpx.Response(200, json=search_response(oats()["product"]))]
    )
    response = await off.search("hafer", page=1, language="de", max_wait=5)
    assert (response.status, len(response.results)) == ("found", 1)
    assert request.call_count == 2


async def test_searches_have_their_own_rate_limit(off_api: respx.MockRouter) -> None:
    """A busy search limit leaves the lookups alone, and the other way round (BAR-08)."""
    search_route(off_api).respond(json=search_response())
    route(off_api, OATS).respond(json=oats())
    searches = SlidingWindow(1, clock=lambda: 100.0)
    lookups = SlidingWindow(1, clock=lambda: 100.0)
    off = client(lookups, search_rate_limit=searches)

    assert (await off.search("a b", page=1, language="de", max_wait=0)).status == "found"
    assert (await off.search("a b", page=1, language="de", max_wait=0)).status == "busy"
    assert (await off.fetch(OATS, max_wait=0)).status == "found"
    assert (await off.fetch(OATS, max_wait=0)).status == "busy"
    await off.aclose()


async def test_without_a_limit_of_their_own_searches_share_the_lookups(
    off_api: respx.MockRouter,
) -> None:
    search_route(off_api).respond(json=search_response())
    route(off_api, OATS).respond(json=oats())
    shared = SlidingWindow(1, clock=lambda: 100.0)
    off = OffClient(OFF_URL, "MealMate/test", rate_limit=shared)
    assert off.search_rate_limit is shared
    assert (await off.search("a b", page=1, language="de", max_wait=0)).status == "found"
    assert (await off.fetch(OATS, max_wait=0)).status == "busy"
    await off.aclose()


async def test_the_search_is_logged_without_the_query(
    off_api: respx.MockRouter, off: OffClient, caplog: pytest.LogCaptureFixture
) -> None:
    """What a user typed is theirs: the log has the page and the query's length only."""
    search_route(off_api).respond(json=search_response(oats()["product"]))
    with caplog.at_level(logging.INFO, logger="app.integrations.off"):
        await off.search("Geheimrezept", page=3, language="de", max_wait=None)
    [record] = [r for r in caplog.records if r.message == "open food facts search"]
    assert (record.page, record.query_length, record.outcome, record.http_status) == (  # type: ignore[attr-defined]
        3,
        12,
        "found",
        200,
    )
    assert "Geheimrezept" not in caplog.text
    assert json.dumps(record.__dict__, default=str).count("Geheimrezept") == 0


def test_settings_give_searches_their_own_limit(make_settings: Any) -> None:
    off = OffClient.from_settings(make_settings(off_search_per_minute=3))
    assert (off.search_rate_limit.limit, off.rate_limit.limit) == (3, 6)
    assert off.search_rate_limit is not off.rate_limit
