"""The Open Food Facts client against recorded responses (BAR-07, BAR-08, BAR-10, plan § 5.9)."""

import gzip
import json
import tracemalloc
import zlib
from collections.abc import AsyncIterator, Iterator
from typing import Any

import anyio
import httpx
import pytest
import respx

from app.core.config import Settings
from app.core.ratelimit import SlidingWindow
from app.domain.units import BaseUnit
from app.integrations.off import FIELDS, OffClient, user_agent
from tests.off import (
    OFF_URL,
    RECORDED_BARCODE,
    RECORDED_MODIFIED_AT,
    USER_AGENT,
    client,
    product_url,
    recorded,
    route,
)


@pytest.fixture
def off_api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=OFF_URL, assert_all_called=False) as mock:
        yield mock


async def test_found_product_from_a_recorded_response(off_api: respx.MockRouter) -> None:
    request = route(off_api, RECORDED_BARCODE).respond(json=recorded("product_found"))

    response = await client().fetch(RECORDED_BARCODE, max_wait=None)

    assert response.status == "found"
    product = response.product
    assert product is not None
    assert product.name("de") == "test_default"
    assert product.brands is None
    assert product.quantity == "100 g"
    assert product.pack == (100, BaseUnit.G)
    assert product.nutrition_basis is BaseUnit.G
    assert product.nutrients == {
        "kcal": 140.5,
        "protein": 4.5,
        "carbs": 10.5,
        "sugar": 12.5,
        "fat": 8.5,
    }
    assert product.category_key == "snacks_sweets"
    assert product.last_modified_at == RECORDED_MODIFIED_AT

    sent = request.calls.last.request
    assert sent.url.path == product_url(RECORDED_BARCODE)
    assert sent.url.params["fields"] == FIELDS
    assert sent.headers["user-agent"] == USER_AGENT
    assert sent.headers["accept"] == "application/json"
    assert sent.headers["accept-encoding"] == "identity"


def test_fields_asked_for() -> None:
    assert FIELDS.split(",") == [
        "code",
        "product_name",
        "product_name_de",
        "product_name_en",
        "generic_name",
        "generic_name_de",
        "generic_name_en",
        "brands",
        "quantity",
        "product_quantity",
        "product_quantity_unit",
        "nutriments",
        "nutrition_data_per",
        "categories_tags",
        "last_modified_t",
    ]


def test_user_agent_and_settings(make_settings: Any) -> None:
    settings: Settings = make_settings(
        version="2.0.0",
        off_base_url="https://off.example/",
        off_user_agent_contact="mailto:owner@example.org",
    )
    assert user_agent(settings) == "MealMate/2.0.0 (mailto:owner@example.org)"
    off = OffClient.from_settings(settings)
    assert off.base_url == "https://off.example"
    assert off.user_agent == "MealMate/2.0.0 (mailto:owner@example.org)"
    assert (off.rate_limit.limit, off.rate_limit.window) == (6, 60)
    assert (off.timeout, off.max_bytes) == (10.0, 1024 * 1024)
    # The nightly job has its own, smaller limit: both together stay within 10 per minute.
    job = OffClient.from_settings(settings, job=True)
    assert (job.rate_limit.limit, job.base_url) == (4, "https://off.example")
    assert job.rate_limit is not off.rate_limit
    custom = make_settings(off_rate_app_per_minute=8, off_rate_job_per_minute=2)
    assert OffClient.from_settings(custom).rate_limit.limit == 8
    assert OffClient.from_settings(custom, job=True).rate_limit.limit == 2


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(404, json=recorded("product_not_found")),
        httpx.Response(404, text="not json"),
        httpx.Response(200, json=recorded("product_not_found")),
        # Another product type (e.g. cosmetics) is redirected to its own site.
        httpx.Response(302, headers={"Location": "https://world.openbeautyfacts.org/"}),
    ],
)
async def test_not_found(off_api: respx.MockRouter, answer: httpx.Response) -> None:
    route(off_api, "12345670").mock(return_value=answer)

    response = await client().fetch("12345670", max_wait=None)

    assert (response.status, response.product) == ("not_found", None)


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500),
        httpx.Response(503, json={"status": "failure"}),
        httpx.Response(429),
        httpx.Response(403),
        httpx.Response(200, text="<html>maintenance</html>"),
        httpx.Response(200, json=["not", "an", "object"]),
        httpx.Response(200, json={"status": "success"}),
        httpx.Response(200, json={"status": "success", "product": "text"}),
        httpx.Response(200, json={"status": "failure", "result": {"id": "invalid_code"}}),
        httpx.Response(200, json={"status": "failure", "result": "product_not_found"}),
        httpx.Response(200, json={"status": "weird", "product": {}}),
    ],
)
async def test_unavailable_answers(
    off_api: respx.MockRouter, answer: httpx.Response, caplog: pytest.LogCaptureFixture
) -> None:
    route(off_api, RECORDED_BARCODE).mock(return_value=answer)

    response = await client().fetch(RECORDED_BARCODE, max_wait=None)

    assert (response.status, response.product) == ("unavailable", None)
    assert "open food facts unavailable" in caplog.messages


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
        httpx.RemoteProtocolError("broken"),
    ],
)
async def test_network_errors(off_api: respx.MockRouter, error: Exception) -> None:
    route(off_api, RECORDED_BARCODE).mock(side_effect=error)

    assert (await client().fetch(RECORDED_BARCODE, max_wait=None)).status == "unavailable"


async def test_unexpected_errors_are_logged_not_raised(
    off_api: respx.MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    route(off_api, RECORDED_BARCODE).mock(side_effect=RuntimeError("bug"))

    assert (await client().fetch(RECORDED_BARCODE, max_wait=None)).status == "unavailable"
    assert "open food facts: unexpected error" in caplog.messages


async def test_total_timeout(off_api: respx.MockRouter) -> None:
    async def slow(_request: httpx.Request) -> httpx.Response:
        await anyio.sleep(5)
        return httpx.Response(200, json=recorded("product_found"))  # pragma: no cover

    route(off_api, RECORDED_BARCODE).mock(side_effect=slow)
    started = anyio.current_time()

    response = await client(timeout=0.2).fetch(RECORDED_BARCODE, max_wait=None)

    assert response.status == "unavailable"
    assert anyio.current_time() - started < 2


async def test_a_declared_body_over_the_cap_is_not_read(off_api: respx.MockRouter) -> None:
    body = json.dumps(recorded("product_found")).encode()
    route(off_api, RECORDED_BARCODE).respond(200, content=body)

    small = client(max_bytes=len(body) - 1)
    assert (await small.fetch(RECORDED_BARCODE, max_wait=None)).status == "unavailable"
    exact = client(max_bytes=len(body))
    assert (await exact.fetch(RECORDED_BARCODE, max_wait=None)).status == "found"


class Endless(httpx.AsyncByteStream):
    """A body without Content-Length that would go on for 1000 KiB."""

    def __init__(self) -> None:
        self.sent = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(1000):
            self.sent += 1
            yield b" " * 1024


async def test_a_streamed_body_over_the_cap_is_abandoned(off_api: respx.MockRouter) -> None:
    stream = Endless()
    route(off_api, RECORDED_BARCODE).mock(return_value=httpx.Response(200, stream=stream))

    response = await client(max_bytes=10 * 1024).fetch(RECORDED_BARCODE, max_wait=None)

    assert response.status == "unavailable"
    assert stream.sent < 20


async def test_busy_when_the_wait_would_be_too_long(off_api: respx.MockRouter) -> None:
    request = route(off_api, RECORDED_BARCODE).respond(json=recorded("product_found"))
    now = 100.0
    off = client(SlidingWindow(1, clock=lambda: now))

    assert (await off.fetch(RECORDED_BARCODE, max_wait=5)).status == "found"
    now += 54  # the next start is 6 s away
    assert (await off.fetch(RECORDED_BARCODE, max_wait=5)).status == "busy"
    assert request.call_count == 1
    now += 6
    assert (await off.fetch(RECORDED_BARCODE, max_wait=5)).status == "found"


# --- compressed bodies ------------------------------------------------------------------------


class Streamed(httpx.AsyncByteStream):
    """A body as it comes from the network, in 16 KiB chunks. (respx reads and decodes a
    plain `content=` body before the client sees it.)"""

    def __init__(self, body: bytes) -> None:
        self.body = body

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self.body), 16 * 1024):
            yield self.body[start : start + 16 * 1024]


def compressed(content: bytes, encoding: str) -> httpx.Response:
    return httpx.Response(200, stream=Streamed(content), headers={"Content-Encoding": encoding})


def gzip_bomb(inflated_mib: int) -> bytes:
    """A small gzip body that inflates to `inflated_mib` MiB of spaces, built without holding
    them."""
    compressor = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
    chunks = [compressor.compress(b" " * 1024 * 1024) for _ in range(inflated_mib)]
    return b"".join(chunks) + compressor.flush()


@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
async def test_a_compressed_body_is_inflated(off_api: respx.MockRouter, encoding: str) -> None:
    body = json.dumps(recorded("product_found")).encode()
    content = gzip.compress(body) if encoding == "gzip" else zlib.compress(body)
    route(off_api, RECORDED_BARCODE).mock(return_value=compressed(content, encoding))

    assert (await client().fetch(RECORDED_BARCODE, max_wait=None)).status == "found"


async def test_a_decompression_bomb_is_abandoned(off_api: respx.MockRouter) -> None:
    """A body far below the cap that inflates far above it is never inflated in full."""
    bomb = gzip_bomb(64)
    assert len(bomb) < 100 * 1024
    route(off_api, RECORDED_BARCODE).mock(return_value=compressed(bomb, "gzip"))
    off = client()

    tracemalloc.start()
    try:
        response = await off.fetch(RECORDED_BARCODE, max_wait=None)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert response.status == "unavailable"
    assert peak < 10 * 1024 * 1024


@pytest.mark.parametrize(
    ("content", "encoding"),
    [
        (b"not gzip at all", "gzip"),
        (gzip.compress(b'{"status": "success", "product": {}}')[:-12], "gzip"),  # truncated
        (b"\x1b\x00\x00", "br"),
    ],
)
async def test_a_broken_or_unexpected_encoding_is_unavailable(
    off_api: respx.MockRouter, content: bytes, encoding: str, caplog: pytest.LogCaptureFixture
) -> None:
    route(off_api, RECORDED_BARCODE).mock(return_value=compressed(content, encoding))

    assert (await client().fetch(RECORDED_BARCODE, max_wait=None)).status == "unavailable"
    assert "open food facts unavailable" in caplog.messages
