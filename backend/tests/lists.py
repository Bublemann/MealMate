"""Helpers for tests of shopping lists."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import update

from app.db.session import Database
from app.models import ShoppingList
from tests.accounts import START, Account

# The check state of every line of a draft (and of unchecked lines while shopping).
UNCHECKED = {
    "checked": False,
    "checked_at": None,
    "checked_by": None,
    "new": False,
    "needs_more": None,
}


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


async def feed_page(api: AsyncClient, user: Account, cursor: str | None = None) -> Any:
    """One page of the list feed (UI-02)."""
    params = {} if cursor is None else {"cursor": cursor}
    response = await api.get("/api/lists", params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def summaries(api: AsyncClient, user: Account) -> list[Any]:
    """Every list in the user's feed, page after page."""
    page = await feed_page(api, user)
    items = page["lists"]
    while page["next_cursor"] is not None:
        page = await feed_page(api, user, page["next_cursor"])
        items += page["lists"]
    return items


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


# --- shopping mode ------------------------------------------------------------------------


async def start_shopping(api: AsyncClient, user: Account, list_id: str) -> Any:
    response = await api.post(f"/api/lists/{list_id}/start-shopping", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


def op(op_type: str, *, at: datetime = START, op_id: str | None = None, **payload: Any) -> Any:
    """An op for `POST /api/lists/{id}/ops`, with a new UUIDv7 unless `op_id` is given."""
    return {
        "op_id": op_id or str(uuid.uuid7()),
        "type": op_type,
        "at": at.isoformat(),
        "payload": payload,
    }


def check(line_key: str, checked: bool = True, **options: Any) -> Any:
    return op("line.check", line_key=line_key, checked=checked, **options)


async def send_ops(api: AsyncClient, user: Account, list_id: str, *ops: Any) -> Response:
    return await api.post(
        f"/api/lists/{list_id}/ops", json={"ops": list(ops)}, headers=user.headers
    )


async def applied(api: AsyncClient, user: Account, list_id: str, *ops: Any) -> Any:
    """Send ops that must all be applied; the list afterwards."""
    response = await send_ops(api, user, list_id, *ops)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [result["status"] for result in body["results"]] == ["applied"] * len(ops), body
    return body["list"]


def results(response: Response) -> list[tuple[str, str | None]]:
    """Per op: its status and code."""
    assert response.status_code == 200, response.text
    return [(item["status"], item["code"]) for item in response.json()["results"]]


def by_key(list_detail: Any, key: str) -> Any:
    return next(item for item in list_detail["lines"] if item["key"] == key)
