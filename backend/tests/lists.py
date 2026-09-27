"""Helpers for tests of shopping lists."""

from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import update

from app.db.session import Database
from app.models import ShoppingList
from tests.accounts import Account


async def create_list(api: AsyncClient, user: Account, name: str | None = None) -> Any:
    body = {} if name is None else {"name": name}
    response = await api.post("/api/lists", json=body, headers=user.headers)
    assert response.status_code == 201, response.text
    return response.json()


async def get_list(api: AsyncClient, user: Account, list_id: str) -> Response:
    return await api.get(f"/api/lists/{list_id}", headers=user.headers)


async def detail(api: AsyncClient, user: Account, list_id: str) -> Any:
    response = await get_list(api, user, list_id)
    assert response.status_code == 200, response.text
    return response.json()


async def add_meal(
    api: AsyncClient, user: Account, list_id: str, meal_id: str, servings: int | None = None
) -> Response:
    body: dict[str, Any] = {"meal_id": meal_id}
    if servings is not None:
        body["servings"] = servings
    return await api.post(f"/api/lists/{list_id}/meals", json=body, headers=user.headers)


async def added(
    api: AsyncClient, user: Account, list_id: str, meal_id: str, servings: int | None = None
) -> Any:
    response = await add_meal(api, user, list_id, meal_id, servings)
    assert response.status_code == 200, response.text
    return response.json()


async def add_extra(api: AsyncClient, user: Account, list_id: str, **body: Any) -> Response:
    return await api.post(f"/api/lists/{list_id}/extra-items", json=body, headers=user.headers)


async def extra_added(api: AsyncClient, user: Account, list_id: str, **body: Any) -> Any:
    response = await add_extra(api, user, list_id, **body)
    assert response.status_code == 201, response.text
    return response.json()


async def summaries(api: AsyncClient, user: Account, **params: Any) -> Any:
    response = await api.get("/api/lists", params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def lines(list_detail: Any) -> dict[str, Any]:
    """The lines by name: display amounts as `(value, unit)` pairs and flags."""
    return {
        line["name"]: (
            [(amount["value"], amount["unit"]) for amount in line["amounts"]],
            line["has_unspecified"],
        )
        for line in list_detail["lines"]
    }


def line(list_detail: Any, name: str) -> Any:
    return next(item for item in list_detail["lines"] if item["name"] == name)


async def set_status(app: FastAPI, list_id: str, status: str) -> None:
    """Put a list into another state directly (shopping mode comes in M5b)."""
    database: Database = app.state.database
    async with database.write_sessions() as session, session.begin():
        await session.execute(
            update(ShoppingList).where(ShoppingList.id == list_id).values(status=status)
        )
