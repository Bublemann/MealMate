"""The Open Food Facts client (plan § 5.9, BAR-05, BAR-07, BAR-08, BAR-10).

Products are read with API v3 at a pinned minor version (`OFF_API_VERSION`, O-4): v3.4 is the
last version with the flat `nutriments` object (`energy-kcal_100g`, ...) and plain
`categories_tags`; v3.5 introduces a new nutrition structure that is still under development, and
v3.6 a new tags schema. `fields=` asks only for what MealMate stores.

The client never raises to its caller. Every request:

- first waits for its turn under the rate limit (a `SlidingWindow`: the app process starts at
  most `MEALMATE_OFF_RATE_APP_PER_MINUTE` requests in any 60 s, the nightly job
  `MEALMATE_OFF_RATE_JOB_PER_MINUTE`, together at most 10); a caller that would wait longer
  than it allows gets `busy`;
- sends `User-Agent: MealMate/<version> (<contact>)` and asks for an uncompressed body
  (`Accept-Encoding: identity`);
- gives up after 10 s in total, and on a body over 1 MiB, read as a stream and abandoned. A
  compressed body is inflated step by step, never more than the rest of the 1 MiB at a time,
  so a small "decompression bomb" cannot make it hold more;
- answers `found` (with the validated product), `not_found` (OFF's `product_not_found` body,
  with HTTP 404 or 200, or a redirect), or `unavailable` (network error, timeout, a body too
  large or not the expected JSON, any other status). OFF redirects a product of another product
  type, such as cosmetics, to that database's site: no food product has the barcode, so a
  redirect is `not_found` (logged with the host it points to, never followed). A 404 without
  OFF's body comes from something in front of OFF (a proxy, a CDN's error page): it says
  nothing about the product, so it is `unavailable`;
- is logged at INFO with its barcode, outcome and HTTP status (no personal data).

The client keeps one connection pool (`httpx.AsyncClient`), opened on first use, so that
consecutive lookups reuse the connection instead of paying for a new TLS handshake each time.
Whoever owns the client closes it (`aclose`): the app's lifespan and the nightly job.

A lookup the user waits for (`retry`) gets one more try when the first failed for a transient
reason: a network error, a timeout, a 5xx, or a 404 without OFF's JSON body. These may come
out differently a moment later, and a user who scans a product then gets its data instead of a
form to fill in. Everything else is final: OFF's `product_not_found` is deterministic, a
redirect points elsewhere every time, and a 429 or another 4xx would only be repeated. Retrying
those would cost a place under the rate limit per scan of an unknown product, and a few such
scans would leave the next lookup `busy`. The retry waits `RETRY_PAUSE_SECONDS`, takes its own
place under the rate limit, but only one it gets within the time the lookup was given anyway
(`max_wait` plus the timeout); otherwise the first answer stands. Background and nightly
refreshes never retry: they try again later anyway.

Everything in a response is untrusted (BAR-10, SEC-13): `OffProduct` keeps only what it can
validate. Texts lose control and bidi characters and are cut to the product field lengths,
nutrients must be finite and plausible (`app.domain.nutrients.plausible`), everything else that
does not fit becomes unknown.
"""

import json
import logging
import math
import zlib
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Annotated, Any, Literal, get_args
from urllib.parse import urlsplit

import anyio
import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, ValidationError

from app.core.config import Settings
from app.core.ratelimit import SlidingWindow
from app.domain.catalog import (
    PACK_QUANTITY_MAX,
    PRODUCT_BRAND_MAX_LENGTH,
    PRODUCT_NAME_MAX_LENGTH,
    PRODUCT_QUANTITY_TEXT_MAX_LENGTH,
    clean_text,
    nutrient_field,
)
from app.domain.categories import guess_category
from app.domain.nutrients import NUTRIENTS, plausible
from app.domain.units import BaseUnit
from app.schemas.users import Language

logger = logging.getLogger(__name__)

OFF_API_VERSION = "v3.4"
PRODUCT_PATH = f"/api/{OFF_API_VERSION}/product/{{barcode}}"
LANGUAGES: tuple[str, ...] = get_args(Language)
FIELDS = ",".join(
    (
        "code",
        "product_name",
        *(f"product_name_{language}" for language in LANGUAGES),
        "generic_name",
        *(f"generic_name_{language}" for language in LANGUAGES),
        "brands",
        "quantity",
        "product_quantity",
        "product_quantity_unit",
        "nutriments",
        "nutrition_data_per",
        "categories_tags",
        "last_modified_t",
    )
)
TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 1024 * 1024
# How long a lookup waits for its turn under the rate limit (BAR-08): with the timeout, a
# lookup is answered within about 15 s.
LOOKUP_MAX_WAIT_SECONDS = 5.0
# The pause before a lookup's second try: long enough for a hiccup to pass, short enough not to
# be noticed next to the lookup itself.
RETRY_PAUSE_SECONDS = 0.75
# The second try is only made when at least this much of the lookup's time is left for it.
RETRY_MIN_SECONDS = 2.0
# Content encodings inflated with zlib (gzip or zlib headers, detected by `_ZLIB_AUTO_WBITS`).
_ZLIB_ENCODINGS = frozenset({"gzip", "x-gzip", "deflate"})
_ZLIB_AUTO_WBITS = zlib.MAX_WBITS | 32
# OFF's statuses of a successful read; "failure" is the other one.
_SUCCESS = frozenset({"success", "success_with_warnings", "success_with_errors"})
_NUMBER_MAX_LENGTH = 32
_UNIT_MAX_LENGTH = 16
_TAGS_MAX = 200
_TAG_MAX_LENGTH = 100
# Unix time of 3000-01-01: later timestamps are not plausible.
_TIMESTAMP_MAX = 32_503_680_000

type OffStatus = Literal["found", "not_found", "unavailable", "busy"]


def _text(value: object, max_length: int) -> str | None:
    return clean_text(value, max_length) if isinstance(value, str) else None


def _number(value: object) -> float | None:
    """A finite number, also from a numeric string (OFF sends some numbers as strings); -0 is
    0."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    if isinstance(value, str) and len(value) > _NUMBER_MAX_LENGTH:
        return None
    try:
        number = float(value)  # an integer too large for a float raises OverflowError
    except ValueError, OverflowError:
        return None
    if not math.isfinite(number):
        return None
    return 0.0 if number == 0 else number


def _pack_quantity(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and 0 < number <= PACK_QUANTITY_MAX else None


def _pack_unit(value: object) -> BaseUnit | None:
    """`g` or `ml` exactly (after cleaning); anything else, such as `mlx` or `kg`, is unknown."""
    if not isinstance(value, str) or len(value) > _UNIT_MAX_LENGTH:
        return None
    text = clean_text(value, _UNIT_MAX_LENGTH)
    return BaseUnit(text) if text in {unit.value for unit in BaseUnit} else None


def _nutrients(value: object) -> dict[str, float]:
    """The plausible values per 100 g/ml by nutrient key; implausible ones are dropped."""
    if not isinstance(value, dict):
        return {}
    values: dict[str, float] = {}
    for nutrient in NUTRIENTS:
        number = _number(value.get(nutrient.off_field))
        if number is not None and plausible(nutrient.key, number):
            values[nutrient.key] = number
    return values


def _timestamp(value: object) -> datetime | None:
    number = _number(value)
    if number is None or not 0 < number < _TIMESTAMP_MAX:
        return None
    return datetime.fromtimestamp(int(number), UTC)


def _tags(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    tags = (_text(item, _TAG_MAX_LENGTH) for item in value[:_TAGS_MAX])
    return tuple(tag for tag in tags if tag)


def _per(value: object) -> str | None:
    """`nutrition_data_per` without spaces, in lower case (`100g`, `100ml`, `serving`)."""
    text = _text(value, 16)
    return None if text is None else "".join(text.split()).lower()


_Name = Annotated[str | None, BeforeValidator(partial(_text, max_length=PRODUCT_NAME_MAX_LENGTH))]


class OffProduct(BaseModel):
    """A product from Open Food Facts, validated and cleaned (BAR-10). Unknown or unusable
    values are None; fields OFF adds are ignored."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    product_name: _Name = None
    product_name_de: _Name = None
    product_name_en: _Name = None
    generic_name: _Name = None
    generic_name_de: _Name = None
    generic_name_en: _Name = None
    brands: Annotated[
        str | None, BeforeValidator(partial(_text, max_length=PRODUCT_BRAND_MAX_LENGTH))
    ] = None
    quantity: Annotated[
        str | None, BeforeValidator(partial(_text, max_length=PRODUCT_QUANTITY_TEXT_MAX_LENGTH))
    ] = None
    product_quantity: Annotated[float | None, BeforeValidator(_pack_quantity)] = None
    product_quantity_unit: Annotated[BaseUnit | None, BeforeValidator(_pack_unit)] = None
    nutrition_data_per: Annotated[str | None, BeforeValidator(_per)] = None
    nutriments: Annotated[dict[str, float], BeforeValidator(_nutrients)] = {}
    categories_tags: Annotated[tuple[str, ...], BeforeValidator(_tags)] = ()
    last_modified_t: Annotated[datetime | None, BeforeValidator(_timestamp)] = None

    def name(self, language: str) -> str | None:
        """The name in `language` if there is one, else the main name, else the generic
        name (in `language`, else the main one)."""
        return (
            getattr(self, f"product_name_{language}", None)
            or self.product_name
            or getattr(self, f"generic_name_{language}", None)
            or self.generic_name
        )

    @property
    def nutrition_basis(self) -> BaseUnit | None:
        """What the nutrients are per: 100 ml (`100ml`, or `100g` for a product sold in ml,
        since OFF's `_100g` values are per 100 ml for liquids), 100 g, or unknown (per serving
        or not given)."""
        match self.nutrition_data_per:
            case "100ml":
                return BaseUnit.ML
            case "100g":
                return BaseUnit.ML if self.product_quantity_unit is BaseUnit.ML else BaseUnit.G
            case _:
                return None

    @property
    def nutrients(self) -> dict[str, float | None]:
        """Every nutrient's value per 100 g/ml; all unknown while the basis is unknown."""
        known = self.nutrition_basis is not None
        return {
            nutrient.key: self.nutriments.get(nutrient.key) if known else None
            for nutrient in NUTRIENTS
        }

    @property
    def pack(self) -> tuple[float, BaseUnit] | tuple[None, None]:
        """The pack size and its unit, only when both are known."""
        if self.product_quantity is None or self.product_quantity_unit is None:
            return None, None
        return self.product_quantity, self.product_quantity_unit

    @property
    def category_key(self) -> str | None:
        return guess_category(self.categories_tags)

    @property
    def last_modified_at(self) -> datetime | None:
        return self.last_modified_t

    def fields(self, language: str) -> dict[str, str | float | None]:
        """The product's values by product field (`name`, ..., `nutrients.kcal`, ...), with
        the name in `language`; nutrients only when the basis is known."""
        pack_quantity, pack_unit = self.pack
        values: dict[str, str | float | None] = {
            "name": self.name(language),
            "brand": self.brands,
            "quantity_text": self.quantity,
            "pack_quantity": pack_quantity,
            "pack_unit": None if pack_unit is None else pack_unit.value,
        }
        if self.nutrition_basis is not None:
            for key, value in self.nutrients.items():
                values[nutrient_field(key)] = value
        return values


@dataclass(frozen=True)
class OffResponse:
    """What asking Open Food Facts gave; `product` is set when `status` is found."""

    status: OffStatus
    product: OffProduct | None = None


BUSY = OffResponse("busy")
NOT_FOUND = OffResponse("not_found")
UNAVAILABLE = OffResponse("unavailable")


class _TooLargeError(Exception):
    pass


@dataclass
class _Exchange:
    """What one request got as far as it went, for the log."""

    http_status: int | None = None


@dataclass(frozen=True)
class _Answer:
    """One request's answer, and whether it is `transient`: a failure that says nothing about
    the product (the network, a timeout, OFF's servers or something in front of them) and may
    come out differently a moment later. Only a transient answer is worth a lookup's second
    try (see the module docstring)."""

    response: OffResponse
    transient: bool = False


_NOT_FOUND_ANSWER = _Answer(NOT_FOUND)


def user_agent(settings: Settings) -> str:
    """`MealMate/<version> (<contact>)`, as OFF asks of API clients (BAR-08)."""
    return f"MealMate/{settings.version} ({settings.off_user_agent_contact})"


class OffClient:
    """Reads products from Open Food Facts at `base_url`, under the `rate_limit`. Owns a
    connection pool once used: close it with `aclose`."""

    def __init__(
        self,
        base_url: str,
        user_agent: str,
        *,
        rate_limit: SlidingWindow,
        timeout: float = TIMEOUT_SECONDS,
        max_bytes: int = MAX_RESPONSE_BYTES,
        retry_pause: float = RETRY_PAUSE_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.retry_pause = retry_pause
        self._client: httpx.AsyncClient | None = None

    @classmethod
    def from_settings(cls, settings: Settings, *, job: bool = False) -> OffClient:
        """The app's client, or with `job` the nightly job's, each with its own rate limit
        (BAR-08)."""
        per_minute = settings.off_rate_job_per_minute if job else settings.off_rate_app_per_minute
        return cls(
            settings.off_base_url, user_agent(settings), rate_limit=SlidingWindow(per_minute)
        )

    @property
    def is_open(self) -> bool:
        """Whether the connection pool is open (it opens on the first request)."""
        return self._client is not None

    def _http(self) -> httpx.AsyncClient:
        """The connection pool, opened on first use: inside the event loop that uses it, which
        for the app is only running once the lifespan has started. Never follows redirects."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=False,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
            )
        return self._client

    async def aclose(self) -> None:
        """Close the connection pool; a later request opens a new one."""
        # A request that arrives while this awaits may open a new pool that nobody closes. That
        # is harmless for the app: uvicorn stops taking requests and lets the running ones
        # finish before the lifespan's shutdown calls this, and the process exits right after.
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    async def fetch(
        self, barcode: str, *, max_wait: float | None, retry: bool = False
    ) -> OffResponse:
        """The product with this (canonical) barcode. Waits at most `max_wait` seconds for its
        turn under the rate limit (None: as long as needed), else answers `busy`. With `retry`
        (a lookup the user waits for), a transient failure gets one more try within `max_wait`
        plus the timeout (see the module docstring)."""
        started = anyio.current_time()
        if not await self.rate_limit.acquire(max_wait):
            _log_outcome(barcode, _Answer(BUSY), _Exchange(), attempt=1)
            return BUSY
        first = await self._request(barcode, time_limit=self.timeout, attempt=1)
        if not retry or not first.transient:
            return first.response
        return await self._retry(barcode, first.response, max_wait=max_wait, started=started)

    async def _retry(
        self, barcode: str, first: OffResponse, *, max_wait: float | None, started: float
    ) -> OffResponse:
        """The second try of a lookup, if it fits into the lookup's time and gets a place under
        the rate limit; else the first answer. An `unavailable` second answer never replaces
        the first one: it cannot say more."""
        deadline = started + (max_wait or 0.0) + self.timeout
        await anyio.sleep(self.retry_pause)
        left = deadline - anyio.current_time()
        if left < RETRY_MIN_SECONDS:
            logger.info("open food facts: no time left to retry", extra={"barcode": barcode})
            return first
        wait_limit = left - RETRY_MIN_SECONDS
        wait = self.rate_limit.reserve(
            wait_limit if max_wait is None else min(max_wait, wait_limit)
        )
        if wait is None:
            logger.info("open food facts: busy, no retry", extra={"barcode": barcode})
            return first
        if wait > 0:
            await self.rate_limit.sleep(wait)
        second = await self._request(barcode, time_limit=min(self.timeout, left - wait), attempt=2)
        return first if second.response.status == "unavailable" else second.response

    async def _request(self, barcode: str, *, time_limit: float, attempt: int) -> _Answer:
        """One request, never raising; its outcome is logged."""
        exchange = _Exchange()
        try:
            with anyio.fail_after(time_limit):
                answer = await self._get(barcode, exchange)
        except TimeoutError:
            answer = _unavailable("timeout", transient=True)
        except httpx.TransportError as exc:  # connecting, reading, the protocol, a proxy
            answer = _unavailable(type(exc).__name__, transient=True)
        except httpx.HTTPError as exc:  # a body that cannot be decoded: the same next time
            answer = _unavailable(type(exc).__name__)
        except _TooLargeError:
            answer = _unavailable("response too large")
        except Exception:
            logger.exception("open food facts: unexpected error")
            answer = _Answer(UNAVAILABLE)
        _log_outcome(barcode, answer, exchange, attempt=attempt)
        return answer

    async def _get(self, barcode: str, exchange: _Exchange) -> _Answer:
        async with self._http().stream(
            "GET", PRODUCT_PATH.format(barcode=barcode), params={"fields": FIELDS}
        ) as response:
            status = exchange.http_status = response.status_code
            if httpx.codes.is_redirect(status):  # any 3xx, with a Location or not
                return _redirected(status, response.headers.get("location"))
            if status not in (httpx.codes.OK, httpx.codes.NOT_FOUND):
                # OFF's servers failing may pass; a 429 or another 4xx would only be repeated.
                return _unavailable(
                    "unexpected status",
                    status=status,
                    transient=httpx.codes.is_server_error(status),
                )
            body = await self._read(response)
        return self._parse(body, status)

    async def _read(self, response: httpx.Response) -> bytes:
        """The (inflated) body, or `_TooLargeError` as soon as it, or what was received,
        exceeds `max_bytes`. An encoding other than gzip or deflate is `httpx.DecodingError`,
        as Open Food Facts was asked not to compress."""
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            raise _TooLargeError
        encoding = response.headers.get("content-encoding", "identity").strip().lower()
        if encoding not in _ZLIB_ENCODINGS | {"identity", ""}:
            raise httpx.DecodingError(f"unexpected content encoding {encoding!r}")
        inflater = zlib.decompressobj(_ZLIB_AUTO_WBITS) if encoding in _ZLIB_ENCODINGS else None
        body = bytearray()
        received = 0
        async for chunk in response.aiter_raw():
            received += len(chunk)
            if received > self.max_bytes:
                raise _TooLargeError
            if inflater is None:
                body += chunk
            else:
                self._inflate(inflater, chunk, body)
        if inflater is not None and not inflater.eof:
            raise httpx.DecodingError("truncated compressed body")
        return bytes(body)

    def _inflate(self, inflater: zlib._Decompress, data: bytes, body: bytearray) -> None:
        """Inflate `data` into `body`, at most the rest of `max_bytes` (plus one byte, to
        notice more) per step."""
        try:
            while data and not inflater.eof:
                body += inflater.decompress(data, self.max_bytes - len(body) + 1)
                self._check_size(body)
                data = inflater.unconsumed_tail
        except zlib.error as exc:
            raise httpx.DecodingError("invalid compressed body") from exc

    def _check_size(self, body: bytearray) -> None:
        if len(body) > self.max_bytes:
            raise _TooLargeError

    @staticmethod
    def _parse(body: bytes, http_status: int) -> _Answer:
        """The answer in a 200 or 404 body: `not_found` only for OFF's own `product_not_found`,
        a product only with 200. A 404 whose body is not a JSON object is no answer from OFF but
        an error page in front of it (a proxy, a CDN): transient."""
        in_front = http_status == httpx.codes.NOT_FOUND
        try:
            document: Any = json.loads(body)
        except ValueError:
            return _unavailable("invalid JSON", status=http_status, transient=in_front)
        if not isinstance(document, dict):
            return _unavailable("unexpected JSON", status=http_status, transient=in_front)
        status = document.get("status")
        result = document.get("result")
        if status == "failure":
            if isinstance(result, dict) and result.get("id") == "product_not_found":
                return _NOT_FOUND_ANSWER
        elif (
            http_status == httpx.codes.OK
            and status in _SUCCESS
            and isinstance(document.get("product"), dict)
        ):
            try:
                return _Answer(OffResponse("found", OffProduct.model_validate(document["product"])))
            except ValidationError:  # pragma: no cover -- every field validator is lenient
                pass
        return _unavailable("unexpected JSON", status=http_status)


def _unavailable(reason: str, *, status: int | None = None, transient: bool = False) -> _Answer:
    """`unavailable`, with a warning that says why."""
    extra: dict[str, object] = {"reason": reason, "transient": transient}
    if status is not None:
        extra["status"] = status
    logger.warning("open food facts unavailable", extra=extra)
    return _Answer(UNAVAILABLE, transient=transient)


def _redirected(status: int, location: str | None) -> _Answer:
    """`not_found` for a redirect: OFF sends one for a product of another product type (such as
    cosmetics) to that database's site, so no food product has this barcode. Logged with the
    host it points to (a relative or broken Location has none), to tell such a redirect from an
    unexpected one."""
    host: str | None = None
    with suppress(ValueError):  # e.g. an unclosed IPv6 bracket
        host = urlsplit(location or "").hostname
    logger.info(
        "open food facts: redirected, not found",
        extra={"reason": "redirect", "status": status, "location_host": host},
    )
    return _NOT_FOUND_ANSWER


def _log_outcome(barcode: str, answer: _Answer, exchange: _Exchange, *, attempt: int) -> None:
    logger.info(
        "open food facts lookup",
        extra={
            "barcode": barcode,
            "outcome": answer.response.status,
            "http_status": exchange.http_status,
            "attempt": attempt,
            "transient": answer.transient,
        },
    )
