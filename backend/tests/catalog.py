"""Helpers for tests of reference data and ingredients."""

from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import update

from app.db.session import Database
from app.models import Ingredient
from tests.accounts import Account

# Valid barcodes (GS1 check digits): EAN-13, EAN-13, UPC-A, EAN-8, UPC-E.
EAN_13 = "4006381333931"
EAN_13_B = "8005516001475"
UPC_A = "036000291452"
EAN_8 = "96385074"
UPC_E = "04252614"

NO_NUTRIENTS = {"kcal": None, "protein": None, "carbs": None, "sugar": None, "fat": None}


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


async def create_from_off(
    api: AsyncClient,
    user: Account,
    name: str,
    barcode: str,
    *,
    edited_fields: list[str] | None = None,
    off_last_modified_at: str | None = None,
    **body: Any,
) -> Any:
    """An ingredient saved from an Open Food Facts proposal (`source` off)."""
    off = {"edited_fields": edited_fields or [], "off_last_modified_at": off_last_modified_at}
    return await create_ingredient(api, user, name, barcode=barcode, off=off, **body)


async def set_stored(app: FastAPI, ingredient_id: str, **values: Any) -> None:
    """Change an ingredient's columns directly, as the API no longer would: a base unit changed
    before D-32 left its amounts as they were, and a g or ml ingredient may still have the piece
    weight and density it had then."""
    database: Database = app.state.database
    async with database.write_sessions() as session, session.begin():
        await session.execute(
            update(Ingredient).where(Ingredient.id == ingredient_id).values(**values)
        )
