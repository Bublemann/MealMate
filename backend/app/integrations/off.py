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
- answers `found` (with the validated product), `not_found` (HTTP 404, OFF's
  `product_not_found`, or a redirect to another product type such as cosmetics), or
  `unavailable` (network error, timeout, any other status, a body too large or not the expected
  JSON).

Everything in a response is untrusted (BAR-10, SEC-13): `OffProduct` keeps only what it can
validate. Texts lose control and bidi characters and are cut to the product field lengths,
nutrients must be finite and plausible (`app.domain.nutrients.plausible`), everything else that
does not fit becomes unknown.
"""

import json
import logging
import math
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Annotated, Any, Literal, get_args

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


def user_agent(settings: Settings) -> str:
    """`MealMate/<version> (<contact>)`, as OFF asks of API clients (BAR-08)."""
    return f"MealMate/{settings.version} ({settings.off_user_agent_contact})"


class OffClient:
    """Reads products from Open Food Facts at `base_url`, under the `rate_limit`."""

    def __init__(
        self,
        base_url: str,
        user_agent: str,
        *,
        rate_limit: SlidingWindow,
        timeout: float = TIMEOUT_SECONDS,
        max_bytes: int = MAX_RESPONSE_BYTES,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.max_bytes = max_bytes

    @classmethod
    def from_settings(cls, settings: Settings, *, job: bool = False) -> OffClient:
        """The app's client, or with `job` the nightly job's, each with its own rate limit
        (BAR-08)."""
        per_minute = settings.off_rate_job_per_minute if job else settings.off_rate_app_per_minute
        return cls(
            settings.off_base_url, user_agent(settings), rate_limit=SlidingWindow(per_minute)
        )

    async def fetch(self, barcode: str, *, max_wait: float | None) -> OffResponse:
        """The product with this (canonical) barcode. Waits at most `max_wait` seconds for its
        turn under the rate limit (None: as long as needed), else answers `busy`."""
        if not await self.rate_limit.acquire(max_wait):
            logger.info("open food facts: busy, lookup refused")
            return BUSY
        try:
            with anyio.fail_after(self.timeout):
                return await self._get(barcode)
        except TimeoutError:
            reason = "timeout"
        except httpx.HTTPError as exc:
            reason = type(exc).__name__
        except _TooLargeError:
            reason = "response too large"
        except Exception:
            logger.exception("open food facts: unexpected error")
            return UNAVAILABLE
        logger.warning("open food facts unavailable", extra={"reason": reason})
        return UNAVAILABLE

    async def _get(self, barcode: str) -> OffResponse:
        async with (
            httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
            ) as client,
            client.stream(
                "GET", PRODUCT_PATH.format(barcode=barcode), params={"fields": FIELDS}
            ) as response,
        ):
            if response.status_code == httpx.codes.NOT_FOUND or response.is_redirect:
                return NOT_FOUND
            if response.status_code != httpx.codes.OK:
                logger.warning(
                    "open food facts unavailable", extra={"status": response.status_code}
                )
                return UNAVAILABLE
            body = await self._read(response)
        return self._parse(body)

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
    def _parse(body: bytes) -> OffResponse:
        try:
            document: Any = json.loads(body)
        except ValueError:
            logger.warning("open food facts unavailable", extra={"reason": "invalid JSON"})
            return UNAVAILABLE
        if not isinstance(document, dict):
            logger.warning("open food facts unavailable", extra={"reason": "unexpected JSON"})
            return UNAVAILABLE
        status = document.get("status")
        result = document.get("result")
        if status == "failure":
            if isinstance(result, dict) and result.get("id") == "product_not_found":
                return NOT_FOUND
        elif status in _SUCCESS and isinstance(document.get("product"), dict):
            try:
                return OffResponse("found", OffProduct.model_validate(document["product"]))
            except ValidationError:  # pragma: no cover -- every field validator is lenient
                pass
        logger.warning("open food facts unavailable", extra={"reason": "unexpected JSON"})
        return UNAVAILABLE
