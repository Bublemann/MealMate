"""Recurring items of the caller's set (LIST-16, D-42)."""

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, Now, TimeZone
from app.db.session import ReadSession, WriteSession
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.recurring import (
    RecurringItem,
    RecurringItemCreate,
    RecurringItemList,
    RecurringItemUpdate,
)
from app.services import recurring

router = APIRouter(prefix="/api/recurring-items", tags=["recurring"], responses=ERROR_RESPONSES)


@router.get("")
async def list_recurring_items(
    principal: CurrentUser, session: ReadSession, now: Now, zone: TimeZone
) -> RecurringItemList:
    """The caller's set (their couple's while in one, else their own), due first."""
    return await recurring.list_items(session, principal, now=now, zone=zone)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_recurring_item(
    body: RecurringItemCreate,
    principal: CurrentUser,
    session: WriteSession,
    now: Now,
    zone: TimeZone,
) -> RecurringItem:
    """Make an ingredient recurring in the caller's set."""
    return await recurring.create_item(session, principal, body, now=now, zone=zone)


@router.patch("/{item_id}")
async def update_recurring_item(
    item_id: str,
    body: RecurringItemUpdate,
    principal: CurrentUser,
    session: WriteSession,
    now: Now,
    zone: TimeZone,
) -> RecurringItem:
    """Change an item's interval, switch it back to automatic, or correct its last purchase
    date."""
    return await recurring.update_item(session, principal, item_id, body, now=now, zone=zone)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_recurring_item(
    item_id: str, principal: CurrentUser, session: WriteSession
) -> None:
    """Remove an item from the caller's set ("Nicht mehr regelmäßig")."""
    await recurring.delete_item(session, principal, item_id)
