"""Open Food Facts stand-in for end-to-end tests (plan § 9). Never part of the production image.

Serves recorded API v3 product responses from fixtures/<barcode>.json, and OFF's own
`product_not_found` envelope with HTTP 404 for every other barcode. Run it next to the app and
point MEALMATE_OFF_BASE_URL at it:

    uv run uvicorn fake_off.app:app --port 18081
"""

import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BARCODE = re.compile(r"[0-9]{8,14}")

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


@app.get("/api/v3/product/{barcode}")
def get_product(barcode: str) -> JSONResponse:
    # OFF answers both /product/<barcode> and /product/<barcode>.json.
    barcode = barcode.removesuffix(".json")
    fixture = FIXTURES / f"{barcode}.json"
    if BARCODE.fullmatch(barcode) and fixture.is_file():
        return JSONResponse(json.loads(fixture.read_text(encoding="utf-8")))
    return JSONResponse(not_found(barcode), status_code=404)
