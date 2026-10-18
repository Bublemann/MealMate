"""The walking order of the caller's couple, or their own without one (REF-01, D-48)."""

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, Now
from app.db.session import ReadSession, WriteSession
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.walking_order import WalkingOrder, WalkingOrderSave
from app.services import walking_order

router = APIRouter(prefix="/api/walking-order", tags=["walking order"], responses=ERROR_RESPONSES)


@router.get("")
async def get_walking_order(principal: CurrentUser, session: ReadSession) -> WalkingOrder:
    """The order the caller's lists are grouped in: the admins' while it follows theirs, else
    the own one."""
    return await walking_order.get_order(session, principal)


@router.put("")
async def save_walking_order(
    body: WalkingOrderSave, principal: CurrentUser, session: WriteSession, now: Now
) -> WalkingOrder:
    """Keep an own order, which stops following the admins' one ("Reihenfolge der Verwaltung
    übernehmen" off)."""
    return await walking_order.save_order(session, principal, body, now=now)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def follow_admin_walking_order(principal: CurrentUser, session: WriteSession) -> None:
    """Follow the admins' order again ("Reihenfolge der Verwaltung übernehmen" on): the own
    order goes."""
    await walking_order.follow_admin(session, principal)
