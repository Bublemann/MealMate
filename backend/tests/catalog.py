"""Helpers for tests of reference data, ingredients and products."""

from typing import Any

from httpx import AsyncClient

from tests.accounts import Account

# Valid barcodes (GS1 check digits): EAN-13, EAN-13, UPC-A, EAN-8, UPC-E.
EAN_13 = "4006381333931"
EAN_13_B = "8005516001475"
UPC_A = "036000291452"
EAN_8 = "96385074"
UPC_E = "04252614"

NO_NUTRIENTS = {"kcal": None, "protein": None, "carbs": None, "sugar": None, "fat": None}


def unknown_nutrition() -> dict[str, Any]:
    info = {"value": None, "source": "unknown", "products_mean": None, "products_count": 0}
    return {key: info for key in NO_NUTRIENTS}


def ref(user: Account) -> dict[str, Any]:
    return {"id": user.id, "display_name": user.display_name, "deactivated": False}


async def category_ids(api: AsyncClient, user: Account) -> dict[str, str]:
    """Category key → id."""
    response = await api.get("/api/categories", headers=user.headers)
    assert response.status_code == 200, response.text
    return {item["key"]: item["id"] for item in response.json()}


async def create_ingredient(api: AsyncClient, user: Account, name: str, **body: Any) -> Any:
    response = await api.post("/api/ingredients", json={"name": name, **body}, headers=user.headers)
    assert response.status_code == 201, response.text
    return response.json()


async def create_product(
    api: AsyncClient, user: Account, ingredient_id: str, barcode: str, **body: Any
) -> Any:
    response = await api.post(
        "/api/products",
        json={"barcode": barcode, "ingredient_id": ingredient_id, **body},
        headers=user.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()
