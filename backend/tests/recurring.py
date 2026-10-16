"""Helpers for tests of recurring items (LIST-16, D-42)."""

from datetime import date
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import update

from app.db.session import Database
from app.models import RecurringItem
from tests.accounts import Account


async def create_recurring(
    api: AsyncClient,
    user: Account,
    ingredient_id: str,
    weeks: int = 4,
    last_purchased_on: date | None = None,
) -> Response:
    body: dict[str, Any] = {"ingredient_id": ingredient_id, "interval_weeks": weeks}
    if last_purchased_on is not None:
        body["last_purchased_on"] = last_purchased_on.isoformat()
    return await api.post("/api/recurring-items", json=body, headers=user.headers)


async def make_recurring(
    api: AsyncClient,
    user: Account,
    ingredient_id: str,
    weeks: int = 4,
    last_purchased_on: date | None = None,
) -> Any:
    """Make an ingredient recurring in the user's set; the new item."""
    response = await create_recurring(api, user, ingredient_id, weeks, last_purchased_on)
    assert response.status_code == 201, response.text
    return response.json()


async def recurring(api: AsyncClient, user: Account) -> Any:
    """The user's set: `{"items": [...], "due_count": n}`."""
    response = await api.get("/api/recurring-items", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def update_recurring(api: AsyncClient, user: Account, item_id: str, **body: Any) -> Response:
    return await api.patch(f"/api/recurring-items/{item_id}", json=body, headers=user.headers)


async def updated(api: AsyncClient, user: Account, item_id: str, **body: Any) -> Any:
    """Change an item; the item as it is now."""
    response = await update_recurring(api, user, item_id, **body)
    assert response.status_code == 200, response.text
    return response.json()


async def store_purchases(app: FastAPI, item_id: str, **values: Any) -> None:
    """Write what purchases from finished lists leave on an item (`last_amount`, `last_unit`,
    `measured_intervals`) directly, without shopping."""
    database: Database = app.state.database
    async with database.write_sessions() as session, session.begin():
        await session.execute(
            update(RecurringItem).where(RecurringItem.id == item_id).values(**values)
        )


async def notices(api: AsyncClient, user: Account) -> Any:
    """The user's unread notices: `{"notices": [...], "count": n}`."""
    response = await api.get("/api/me/notices", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()
