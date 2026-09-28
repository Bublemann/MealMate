"""Helpers for tests of the Open Food Facts integration (BAR, plan § 9).

`fixtures/off/product_found.json` and `product_not_found.json` are responses recorded by Open
Food Facts' own integration tests: `get-existing-product.json` and `get-unexisting-product.json`
in openfoodfacts-server's `tests/integration/expected_test_results/api_v3_product_read/`
(commit e6442e71, 2026-09-26), reduced to the fields MealMate asks for. `last_modified_t`, which
those tests ignore, is set to 2026-01-01. Other responses are built with `product_response()`.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import respx

from app.core.ratelimit import SlidingWindow
from app.integrations.off import OffClient
from app.services.off_refresh import OffRefresher

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "off"
OFF_URL = "https://off.test"
USER_AGENT = "MealMate/test (https://example.org/mealmate)"
RECORDED_BARCODE = "4260392550101"
RECORDED_MODIFIED_AT = datetime(2026, 1, 1, tzinfo=UTC)
# Synthetic barcodes (GS1 prefix 2: in-store numbers), valid check digits.
OATS = "2000000000015"
MILK = "2000000000022"
UNKNOWN = "2000000000046"


def recorded(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def product_response(barcode: str, **product: Any) -> dict[str, Any]:
    """An API v3 response with this product, as OFF sends it."""
    return {
        "code": barcode,
        "errors": [],
        "product": {"code": barcode, **product},
        "result": {"id": "product_found", "lc_name": "Product found", "name": "Product found"},
        "status": "success",
        "warnings": [],
    }


def oats(**changes: Any) -> dict[str, Any]:
    """A German and English product with all nutrients per 100 g."""
    product: dict[str, Any] = {
        "product_name": "Rolled Oats",
        "product_name_de": "Haferflocken",
        "product_name_en": "Rolled Oats",
        "generic_name": "Rolled oats",
        "brands": "MealMate Test Kitchen",
        "quantity": "500 g",
        "product_quantity": 500,
        "product_quantity_unit": "g",
        "nutrition_data_per": "100g",
        "nutriments": {
            "energy-kcal_100g": 372,
            "proteins_100g": 13.5,
            "carbohydrates_100g": 58.7,
            "sugars_100g": 0.7,
            "fat_100g": 7,
        },
        "categories_tags": ["en:plant-based-foods", "en:breakfasts", "en:cereals-and-potatoes"],
        "last_modified_t": int(RECORDED_MODIFIED_AT.timestamp()),
    }
    return product_response(OATS, **(product | changes))


def modified(days: int) -> int:
    """`last_modified_t` some days after the recorded one."""
    return int((RECORDED_MODIFIED_AT + timedelta(days=days)).timestamp())


def product_url(barcode: str) -> str:
    return f"/api/v3.4/product/{barcode}"


def route(mock: respx.MockRouter, barcode: str) -> respx.Route:
    return mock.get(product_url(barcode))


def search_route(mock: respx.MockRouter) -> respx.Route:
    return mock.get("/cgi/search.pl")


def search_response(*products: dict[str, Any], count: int | None = None) -> dict[str, Any]:
    """A page of `/cgi/search.pl?json=1`, as OFF sends it; `products` are API product objects
    (e.g. `oats()["product"]`)."""
    return {
        "count": len(products) if count is None else count,
        "page": 1,
        "page_count": len(products),
        "page_size": 20,
        "products": list(products),
        "skip": 0,
    }


def unlimited_rate() -> SlidingWindow:
    return SlidingWindow(1_000_000)


def client(
    rate_limit: SlidingWindow | None = None,
    *,
    search_rate_limit: SlidingWindow | None = None,
    **options: Any,
) -> OffClient:
    """A client for the mocked OFF_URL; a lookup's second try follows without a pause."""
    options = {"retry_pause": 0.0} | options
    return OffClient(
        OFF_URL,
        USER_AGENT,
        rate_limit=rate_limit or unlimited_rate(),
        search_rate_limit=search_rate_limit or unlimited_rate(),
        **options,
    )


def refresher(
    rate_limit: SlidingWindow | None = None,
    *,
    search_rate_limit: SlidingWindow | None = None,
    **options: Any,
) -> OffRefresher:
    return OffRefresher(
        client(rate_limit, search_rate_limit=search_rate_limit),
        max_age=timedelta(days=30),
        **options,
    )
