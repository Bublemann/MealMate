"""Open Food Facts stand-in for end-to-end tests (plan § 9). Never part of the production image.

Serves recorded API v3 product responses from fixtures/<barcode>.json, at `/api/v3/product/…`
and at pinned minor versions such as `/api/v3.4/product/…` (the app's client pins one, O-4), and
OFF's own `product_not_found` envelope with HTTP 404 for every other barcode. Like OFF, it
ignores `fields=` and other query parameters. Run it next to the app and point
MEALMATE_OFF_BASE_URL at it:

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
- any other barcode, e.g. 2000000000046: not found.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BARCODE = re.compile(r"[0-9]{8,14}")
VERSION = re.compile(r"v3(\.[0-9]+)?")
SLOW_BARCODE = "2000000000053"
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
        await asyncio.sleep(float(os.environ.get("FAKE_OFF_SLOW_SECONDS", SLOW_SECONDS)))
    return JSONResponse(json.loads(fixture.read_text(encoding="utf-8")))
