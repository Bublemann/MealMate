"""Open Food Facts stand-in for end-to-end tests (plan § 9). Never part of the production image.

Serves recorded API v3 product responses from fixtures/<barcode>.json, at `/api/v3/product/…`
and at pinned minor versions such as `/api/v3.4/product/…` (the app's client pins one, O-4), and
OFF's own `product_not_found` envelope with HTTP 404 for every other barcode. Like OFF, it
ignores `fields=` and other query parameters.

It also answers OFF's full-text search, `/cgi/search.pl?search_terms=…&page=…&page_size=…`,
which the app uses to find a product by name: every fixture product (but the hostile one) whose
name or brand contains each of the words, ignoring case, in the shape OFF sends (`count`,
`page`, `page_size`, `products`), `page_size` (at most 100, default 20) per page. The country
filter and the order are OFF's business and ignored here; products come in barcode order. A
search that finds the slow red lentils ("linsen") is answered late, like their lookup. Run it
next to the app and point MEALMATE_OFF_BASE_URL at it:

    uv run uvicorn fake_off.app:app --port 18081

The fixtures (all synthetic: GS1 prefix 2 is for in-store numbers):

- 2000000000015 rolled oats: English and German names, nutrients per 100 g, a category;
- 2000000000022 whole milk: German name, sold in ml, nutrients per 100 ml (`100g` in OFF terms);
- 2000000000039 sea salt: no nutrition data at all;
- 2000000000053 red lentils: answered only after `SLOW_SECONDS` (default 15 s), longer than the
  app's 10 s timeout, so the app reports OFF as unavailable;
- 2000000000060 a hostile product: control and bidi characters, an overlong brand, absurd,
  negative and non-numeric nutrients (the app must clean or drop all of it, BAR-10);
- 2000000000077 young gouda: German and English names, nutrients per 100 g, a cheese (Firefox's
  product in tests/test_barcodes.py, as oats are WebKit's and milk is Chromium's);
- for the name search (and readable by barcode, like any product): 2000000000084 and
  2000000000091, spaghetti of two brands ("Pastificio Testa", "Nudelwerk Muster");
  2000000000107 strained tomatoes ("Passierte Tomaten"); 2000000000114 an oat drink
  ("Haferdrink", in ml), which a search for "hafer" finds together with the oats;
- any other barcode, e.g. 2000000000046: not found.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BARCODE = re.compile(r"[0-9]{8,14}")
VERSION = re.compile(r"v3(\.[0-9]+)?")
SLOW_BARCODE = "2000000000053"
HOSTILE_BARCODE = "2000000000060"
SEARCHED_FIELDS = ("product_name", "product_name_de", "product_name_en", "brands")
SEARCH_PAGE_SIZE_MAX = 100
# Seconds before the slow barcode is answered (FAKE_OFF_SLOW_SECONDS overrides it).
SLOW_SECONDS = 15.0

app = FastAPI(title="Fake Open Food Facts", docs_url=None, redoc_url=None, openapi_url=None)


def not_found(barcode: str) -> dict[str, Any]:
    """The body OFF returns for an unknown product."""
    return {
        "code": barcode,
        "errors": [
            {
                "field": {"id": "code", "value": barcode},
                "impact": {"id": "failure", "lc_name": "Failure", "name": "Failure"},
                "message": {"id": "product_not_found", "lc_name": "", "name": ""},
            }
        ],
        "result": {
            "id": "product_not_found",
            "lc_name": "Product not found",
            "name": "Product not found",
        },
        "status": "failure",
        "warnings": [],
    }


@app.get("/api/{version}/product/{barcode}")
async def get_product(version: str, barcode: str) -> JSONResponse:
    # OFF answers both /product/<barcode> and /product/<barcode>.json.
    barcode = barcode.removesuffix(".json")
    fixture = FIXTURES / f"{barcode}.json"
    if not VERSION.fullmatch(version) or not BARCODE.fullmatch(barcode) or not fixture.is_file():
        return JSONResponse(not_found(barcode), status_code=404)
    if barcode == SLOW_BARCODE:
        await asyncio.sleep(_slow_down())
    return JSONResponse(json.loads(fixture.read_text(encoding="utf-8")))


def _slow_down() -> float:
    return float(os.environ.get("FAKE_OFF_SLOW_SECONDS", SLOW_SECONDS))


def _searchable() -> list[dict[str, Any]]:
    """The fixture products the search looks through, in barcode order."""
    products = []
    for fixture in sorted(FIXTURES.glob("*.json")):
        if fixture.stem != HOSTILE_BARCODE:
            products.append(json.loads(fixture.read_text(encoding="utf-8"))["product"])
    return products


def _matches(product: dict[str, Any], words: list[str]) -> bool:
    text = " ".join(str(product.get(field) or "") for field in SEARCHED_FIELDS).casefold()
    return all(word in text for word in words)


@app.get("/cgi/search.pl")
async def search(
    search_terms: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=SEARCH_PAGE_SIZE_MAX),
) -> JSONResponse:
    words = search_terms.casefold().split()
    found = [product for product in _searchable() if words and _matches(product, words)]
    if any(product["code"] == SLOW_BARCODE for product in found):
        await asyncio.sleep(_slow_down())
    skip = (page - 1) * page_size
    return JSONResponse(
        {
            "count": len(found),
            "page": page,
            "page_count": len(found[skip : skip + page_size]),
            "page_size": page_size,
            "products": found[skip : skip + page_size],
            "skip": skip,
        }
    )
