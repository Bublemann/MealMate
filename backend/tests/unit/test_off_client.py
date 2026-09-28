"""The Open Food Facts client against recorded responses (BAR-07, BAR-08, BAR-10, plan § 5.9)."""

import gzip
import json
import logging
import tracemalloc
import zlib
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import anyio
import httpx
import pytest
import respx

from app.core.config import Settings
from app.core.ratelimit import SlidingWindow
from app.domain.units import BaseUnit
from app.integrations import off as off_module
from app.integrations.off import FIELDS, OffClient, user_agent
from tests.off import (
    OFF_URL,
    RECORDED_BARCODE,
    RECORDED_MODIFIED_AT,
    UNKNOWN,
    USER_AGENT,
    client,
    product_url,
    recorded,
    route,
)

type ClientMaker = Callable[..., OffClient]

NOT_FOUND_ANSWER = httpx.Response(404, json=recorded("product_not_found"))
FOUND_ANSWER = httpx.Response(200, json=recorded("product_found"))
# A transient failure, which a lookup asks again after.
FAILED_ANSWER = httpx.Response(503)


@pytest.fixture
def off_api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=OFF_URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
async def make_client() -> AsyncIterator[ClientMaker]:
    """`tests.off.client`, closed after the test like the app and the nightly job close theirs,
    so that no connection pool is left to the garbage collector."""
    made: list[OffClient] = []

    def make(rate_limit: SlidingWindow | None = None, **options: Any) -> OffClient:
        off = client(rate_limit, **options)
        made.append(off)
        return off

    yield make
    for off in made:
        await off.aclose()


async def test_found_product_from_a_recorded_response(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    request = route(off_api, RECORDED_BARCODE).respond(json=recorded("product_found"))

    response = await make_client().fetch(RECORDED_BARCODE, max_wait=None)

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
    assert (off.timeout, off.max_bytes, off.retry_pause) == (10.0, 1024 * 1024, 0.75)
    assert not off.is_open  # the connection pool opens on the first request
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
        httpx.Response(200, json=recorded("product_not_found")),
    ],
)
async def test_not_found(
    off_api: respx.MockRouter, answer: httpx.Response, make_client: ClientMaker
) -> None:
    """Only Open Food Facts' own `product_not_found` body means "not found". It is final: even
    a lookup does not ask again, which would only cost a place under the rate limit."""
    request = route(off_api, "12345670").mock(side_effect=[answer, FOUND_ANSWER])

    response = await make_client().fetch("12345670", max_wait=5, retry=True)

    assert (response.status, response.product) == ("not_found", None)
    assert request.call_count == 1


@pytest.mark.parametrize(
    ("answer", "host"),
    [
        # OFF's redirect for a product of another type, here cosmetics.
        (
            httpx.Response(302, headers={"Location": "https://world.openbeautyfacts.org/p/1"}),
            "world.openbeautyfacts.org",
        ),
        (httpx.Response(301, headers={"Location": "https://off.test/elsewhere"}), "off.test"),
        (httpx.Response(307, headers={"Location": "/api/v3.4/product/4260392550101"}), None),
        (httpx.Response(308, headers={"Location": "https://[broken"}), None),
        (httpx.Response(304), None),
    ],
)
async def test_a_redirect_is_not_found(
    off_api: respx.MockRouter,
    answer: httpx.Response,
    host: str | None,
    caplog: pytest.LogCaptureFixture,
    make_client: ClientMaker,
) -> None:
    """No food product has the barcode, which is final: never followed, never asked again.
    Logged with the host it points to."""
    request = route(off_api, RECORDED_BARCODE).mock(return_value=answer)

    with caplog.at_level(logging.INFO, logger="app.integrations.off"):
        response = await make_client().fetch(RECORDED_BARCODE, max_wait=5, retry=True)

    assert (response.status, response.product) == ("not_found", None)
    assert request.call_count == 1  # and no redirect followed (nothing else is mocked)
    [record] = [r for r in caplog.records if r.message == "open food facts: redirected, not found"]
    assert record.levelno == logging.INFO
    assert (record.reason, record.status, record.location_host) == (  # type: ignore[attr-defined]
        "redirect",
        answer.status_code,
        host,
    )


@pytest.mark.parametrize(
    ("answer", "transient"),
    [
        # Open Food Facts' servers failing, which may pass.
        (httpx.Response(500), True),
        (httpx.Response(503, json={"status": "failure"}), True),
        # A 404 without Open Food Facts' body comes from something in front of it (a proxy, a
        # CDN's error page), which may pass too.
        (httpx.Response(404, text="<html>Not Found</html>"), True),
        (httpx.Response(404), True),
        (httpx.Response(404, json=["not", "an", "object"]), True),
        # Answers that would only be repeated.
        (httpx.Response(429), False),
        (httpx.Response(403), False),
        (httpx.Response(200, text="<html>maintenance</html>"), False),
        (httpx.Response(200, json=["not", "an", "object"]), False),
        (httpx.Response(200, json={"status": "success"}), False),
        (httpx.Response(200, json={"status": "success", "product": "text"}), False),
        (httpx.Response(200, json={"status": "failure", "result": {"id": "invalid_code"}}), False),
        (httpx.Response(200, json={"status": "failure", "result": "product_not_found"}), False),
        (httpx.Response(200, json={"status": "weird", "product": {}}), False),
        (httpx.Response(404, json={"status": "failure", "result": {"id": "invalid_code"}}), False),
        (httpx.Response(404, json=recorded("product_found")), False),
    ],
)
async def test_unavailable_answers(
    off_api: respx.MockRouter,
    answer: httpx.Response,
    transient: bool,
    caplog: pytest.LogCaptureFixture,
    make_client: ClientMaker,
) -> None:
    """Unavailable; a lookup asks again only after a transient failure."""
    request = route(off_api, RECORDED_BARCODE).mock(return_value=answer)

    response = await make_client().fetch(RECORDED_BARCODE, max_wait=5, retry=True)

    assert (response.status, response.product) == ("unavailable", None)
    assert "open food facts unavailable" in caplog.messages
    assert request.call_count == (2 if transient else 1)


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("slow"),
        httpx.RemoteProtocolError("broken"),
    ],
)
async def test_network_errors(
    off_api: respx.MockRouter, error: Exception, make_client: ClientMaker
) -> None:
    """Unavailable, and transient: a lookup asks again."""
    request = route(off_api, RECORDED_BARCODE).mock(side_effect=error)
    off = make_client()

    assert (await off.fetch(RECORDED_BARCODE, max_wait=None)).status == "unavailable"
    assert request.call_count == 1
    assert (await off.fetch(RECORDED_BARCODE, max_wait=5, retry=True)).status == "unavailable"
    assert request.call_count == 3


async def test_unexpected_errors_are_logged_not_raised(
    off_api: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
    make_client: ClientMaker,
) -> None:
    """Unavailable, and not asked again: nothing says that the error would pass."""
    request = route(off_api, RECORDED_BARCODE).mock(side_effect=RuntimeError("bug"))

    response = await make_client().fetch(RECORDED_BARCODE, max_wait=5, retry=True)

    assert response.status == "unavailable"
    assert "open food facts: unexpected error" in caplog.messages
    assert request.call_count == 1


async def test_total_timeout(off_api: respx.MockRouter, make_client: ClientMaker) -> None:
    async def slow(_request: httpx.Request) -> httpx.Response:
        await anyio.sleep(5)
        return httpx.Response(200, json=recorded("product_found"))  # pragma: no cover

    route(off_api, RECORDED_BARCODE).mock(side_effect=slow)
    started = anyio.current_time()

    response = await make_client(timeout=0.2).fetch(RECORDED_BARCODE, max_wait=None)

    assert response.status == "unavailable"
    assert anyio.current_time() - started < 2


async def test_a_declared_body_over_the_cap_is_not_read(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    body = json.dumps(recorded("product_found")).encode()
    route(off_api, RECORDED_BARCODE).respond(200, content=body)

    small = make_client(max_bytes=len(body) - 1)
    assert (await small.fetch(RECORDED_BARCODE, max_wait=None)).status == "unavailable"
    exact = make_client(max_bytes=len(body))
    assert (await exact.fetch(RECORDED_BARCODE, max_wait=None)).status == "found"


class Endless(httpx.AsyncByteStream):
    """A body without Content-Length that would go on for 1000 KiB."""

    def __init__(self) -> None:
        self.sent = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(1000):
            self.sent += 1
            yield b" " * 1024


async def test_a_streamed_body_over_the_cap_is_abandoned(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    stream = Endless()
    request = route(off_api, RECORDED_BARCODE).mock(return_value=httpx.Response(200, stream=stream))

    response = await make_client(max_bytes=10 * 1024).fetch(
        RECORDED_BARCODE, max_wait=5, retry=True
    )

    assert response.status == "unavailable"
    assert stream.sent < 20
    assert request.call_count == 1  # the same body would come again


async def test_busy_when_the_wait_would_be_too_long(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    request = route(off_api, RECORDED_BARCODE).respond(json=recorded("product_found"))
    now = 100.0
    off = make_client(SlidingWindow(1, clock=lambda: now))

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
async def test_a_compressed_body_is_inflated(
    off_api: respx.MockRouter, encoding: str, make_client: ClientMaker
) -> None:
    body = json.dumps(recorded("product_found")).encode()
    content = gzip.compress(body) if encoding == "gzip" else zlib.compress(body)
    route(off_api, RECORDED_BARCODE).mock(return_value=compressed(content, encoding))

    assert (await make_client().fetch(RECORDED_BARCODE, max_wait=None)).status == "found"


async def test_a_decompression_bomb_is_abandoned(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    """A body far below the cap that inflates far above it is never inflated in full."""
    bomb = gzip_bomb(64)
    assert len(bomb) < 100 * 1024
    route(off_api, RECORDED_BARCODE).mock(return_value=compressed(bomb, "gzip"))
    off = make_client()

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
    off_api: respx.MockRouter,
    content: bytes,
    encoding: str,
    caplog: pytest.LogCaptureFixture,
    make_client: ClientMaker,
) -> None:
    """Unavailable, and not asked again: the same body would come again."""
    request = route(off_api, RECORDED_BARCODE).mock(return_value=compressed(content, encoding))

    response = await make_client().fetch(RECORDED_BARCODE, max_wait=5, retry=True)

    assert response.status == "unavailable"
    assert "open food facts unavailable" in caplog.messages
    assert request.call_count == 1


# --- one connection pool --------------------------------------------------------------------------


async def test_one_connection_pool_for_all_requests(
    off_api: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    make_client: ClientMaker,
) -> None:
    """Consecutive requests share one `httpx.AsyncClient` (keep-alive); `aclose` closes it and
    a later request opens a new one."""
    created: list[httpx.AsyncClient] = []
    options: list[dict[str, Any]] = []

    class Recorded(httpx.AsyncClient):
        def __init__(self, **kwargs: Any) -> None:
            options.append(kwargs)
            super().__init__(**kwargs)
            created.append(self)

    monkeypatch.setattr(off_module.httpx, "AsyncClient", Recorded)
    request = route(off_api, RECORDED_BARCODE).respond(json=recorded("product_found"))
    off = make_client()

    for _ in range(3):
        assert (await off.fetch(RECORDED_BARCODE, max_wait=None)).status == "found"

    assert len(created) == 1
    assert off.is_open
    assert options[0]["follow_redirects"] is False
    assert {sent.headers["user-agent"] for sent, _ in request.calls} == {USER_AGENT}
    await off.aclose()
    assert created[0].is_closed
    assert not off.is_open
    await off.aclose()  # closing twice is harmless

    assert (await off.fetch(RECORDED_BARCODE, max_wait=None)).status == "found"
    assert len(created) == 2
    await off.aclose()


# --- a lookup's second try ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answers", "status"),
    [
        ([FAILED_ANSWER, FOUND_ANSWER], "found"),
        ([httpx.Response(404, text="<html>Not Found</html>"), FOUND_ANSWER], "found"),
        ([httpx.ConnectError("refused"), FOUND_ANSWER], "found"),
        ([FAILED_ANSWER, NOT_FOUND_ANSWER], "not_found"),
        ([httpx.Response(502), FAILED_ANSWER], "unavailable"),
        ([FAILED_ANSWER, httpx.Response(429)], "unavailable"),
    ],
)
async def test_a_lookup_tries_once_more(
    off_api: respx.MockRouter,
    answers: list[httpx.Response | Exception],
    status: str,
    make_client: ClientMaker,
) -> None:
    request = route(off_api, RECORDED_BARCODE).mock(side_effect=answers)

    response = await make_client().fetch(RECORDED_BARCODE, max_wait=5, retry=True)

    assert response.status == status
    assert request.call_count == 2


async def test_a_found_product_is_not_asked_for_again(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    request = route(off_api, RECORDED_BARCODE).mock(side_effect=[FOUND_ANSWER, NOT_FOUND_ANSWER])

    assert (await make_client().fetch(RECORDED_BARCODE, max_wait=5, retry=True)).status == "found"
    assert request.call_count == 1


async def test_only_lookups_try_again(off_api: respx.MockRouter, make_client: ClientMaker) -> None:
    """Refreshes (without `retry`) take the first answer: they try again another time."""
    request = route(off_api, RECORDED_BARCODE).mock(side_effect=[FAILED_ANSWER, FOUND_ANSWER])

    assert (await make_client().fetch(RECORDED_BARCODE, max_wait=0)).status == "unavailable"
    assert request.call_count == 1


async def test_the_second_try_follows_a_short_pause(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    route(off_api, RECORDED_BARCODE).mock(side_effect=[FAILED_ANSWER, FOUND_ANSWER])
    started = anyio.current_time()

    response = await make_client(retry_pause=0.2).fetch(RECORDED_BARCODE, max_wait=5, retry=True)

    assert response.status == "found"
    assert anyio.current_time() - started >= 0.2


async def test_the_second_try_takes_a_place_under_the_rate_limit(
    off_api: respx.MockRouter,
    make_client: ClientMaker,
) -> None:
    """It waits for its place like any request, as long as the lookup's time allows."""
    request = route(off_api, RECORDED_BARCODE).mock(side_effect=[FAILED_ANSWER, FOUND_ANSWER])
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    rate = SlidingWindow(1, window=3.0, clock=lambda: 100.0, sleep=sleep)
    response = await make_client(rate).fetch(RECORDED_BARCODE, max_wait=5, retry=True)

    assert response.status == "found"
    assert request.call_count == 2
    assert slept == [3.0]
    assert len(rate._starts) == 2


async def test_no_second_try_without_a_place_under_the_rate_limit(
    off_api: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
    make_client: ClientMaker,
) -> None:
    request = route(off_api, RECORDED_BARCODE).mock(side_effect=[FAILED_ANSWER, FOUND_ANSWER])
    rate = SlidingWindow(1, clock=lambda: 100.0)  # the next place is 60 s away

    with caplog.at_level(logging.INFO, logger="app.integrations.off"):
        response = await make_client(rate).fetch(RECORDED_BARCODE, max_wait=5, retry=True)

    assert response.status == "unavailable"
    assert request.call_count == 1
    assert "open food facts: busy, no retry" in caplog.messages
    assert len(rate._starts) == 1  # nothing reserved for the retry


async def test_a_busy_lookup_is_not_tried_again(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    request = route(off_api, RECORDED_BARCODE).respond(json=recorded("product_found"))
    off = make_client(SlidingWindow(1, clock=lambda: 100.0))
    assert (await off.fetch(RECORDED_BARCODE, max_wait=5)).status == "found"

    assert (await off.fetch(RECORDED_BARCODE, max_wait=5, retry=True)).status == "busy"
    assert request.call_count == 1


async def test_no_second_try_when_the_lookups_time_is_used_up(
    off_api: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
    make_client: ClientMaker,
) -> None:
    """A lookup gets `max_wait` plus the timeout in all; the second try needs 2 s of it."""
    request = route(off_api, RECORDED_BARCODE).mock(side_effect=[FAILED_ANSWER, FOUND_ANSWER])

    with caplog.at_level(logging.INFO, logger="app.integrations.off"):
        response = await make_client(timeout=1.5).fetch(RECORDED_BARCODE, max_wait=0, retry=True)

    assert response.status == "unavailable"
    assert request.call_count == 1
    assert "open food facts: no time left to retry" in caplog.messages


async def test_the_second_try_ends_with_the_lookups_time(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    """After a first try that timed out, the second gets only what is left of the lookup."""

    started_requests: list[float] = []

    async def slow(_request: httpx.Request) -> httpx.Response:
        started_requests.append(anyio.current_time())
        await anyio.sleep(5)
        return httpx.Response(200, json=recorded("product_found"))  # pragma: no cover

    route(off_api, RECORDED_BARCODE).mock(side_effect=slow)
    started = anyio.current_time()

    # 2.7 s in all: 0.2 s for the first try, then 2.5 s left, of which the second may use 0.2 s.
    response = await make_client(timeout=0.2).fetch(RECORDED_BARCODE, max_wait=2.5, retry=True)

    assert response.status == "unavailable"
    assert len(started_requests) == 2
    assert anyio.current_time() - started < 1.5


async def test_a_lookup_without_a_wait_limit_may_try_again(
    off_api: respx.MockRouter, make_client: ClientMaker
) -> None:
    request = route(off_api, RECORDED_BARCODE).mock(side_effect=[FAILED_ANSWER, FOUND_ANSWER])

    assert (
        await make_client().fetch(RECORDED_BARCODE, max_wait=None, retry=True)
    ).status == "found"
    assert request.call_count == 2


# --- the log ------------------------------------------------------------------------------------


def lookups(caplog: pytest.LogCaptureFixture) -> list[tuple[str, str, int | None, int, bool]]:
    return [
        (record.barcode, record.outcome, record.http_status, record.attempt, record.transient)  # type: ignore[attr-defined]
        for record in caplog.records
        if record.message == "open food facts lookup" and record.levelno == logging.INFO
    ]


async def test_every_outcome_is_logged(
    off_api: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
    make_client: ClientMaker,
) -> None:
    """At INFO, with the barcode, the outcome, the HTTP status and whether a failure was
    transient (the reason for a second try): no personal data."""
    route(off_api, RECORDED_BARCODE).respond(json=recorded("product_found"))
    route(off_api, UNKNOWN).mock(side_effect=[FAILED_ANSWER, NOT_FOUND_ANSWER])
    route(off_api, "12345670").mock(side_effect=httpx.ConnectError("refused"))
    off = make_client(SlidingWindow(4, clock=lambda: 100.0))

    with caplog.at_level(logging.INFO, logger="app.integrations.off"):
        await off.fetch(RECORDED_BARCODE, max_wait=None)
        await off.fetch(UNKNOWN, max_wait=5, retry=True)
        await off.fetch("12345670", max_wait=None)
        await off.fetch(RECORDED_BARCODE, max_wait=0)

    assert lookups(caplog) == [
        (RECORDED_BARCODE, "found", 200, 1, False),
        (UNKNOWN, "unavailable", 503, 1, True),
        (UNKNOWN, "not_found", 404, 2, False),
        ("12345670", "unavailable", None, 1, True),
        (RECORDED_BARCODE, "busy", None, 1, False),
    ]
