"""The own couple and couple requests (CPL-01, CPL-05)."""

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, Now
from app.db.session import ReadSession, WriteSession
from app.schemas.couples import CoupleRequestCreate, CoupleState
from app.schemas.errors import ERROR_RESPONSES
from app.services import couples

router = APIRouter(prefix="/api/couple", tags=["couple"], responses=ERROR_RESPONSES)


@router.get("")
async def get_couple(principal: CurrentUser, session: ReadSession) -> CoupleState:
    """The partner, if any, and pending requests."""
    return await couples.get_state(session, principal)


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_couple_request(
    body: CoupleRequestCreate, principal: CurrentUser, session: WriteSession, now: Now
) -> CoupleState:
    """Send a couple request to another active user."""
    return await couples.send_request(session, principal, body.user_id, now=now)


@router.post("/requests/{request_id}/accept")
async def accept_couple_request(
    request_id: str, principal: CurrentUser, session: WriteSession, now: Now
) -> CoupleState:
    """Accept a request sent to you; cancels all other pending requests of both users."""
    return await couples.accept(session, principal, request_id, now=now)


@router.post("/requests/{request_id}/decline")
async def decline_couple_request(
    request_id: str, principal: CurrentUser, session: WriteSession
) -> CoupleState:
    """Decline a request sent to you."""
    return await couples.decline(session, principal, request_id)


@router.post("/requests/{request_id}/cancel")
async def cancel_couple_request(
    request_id: str, principal: CurrentUser, session: WriteSession
) -> CoupleState:
    """Withdraw your own request."""
    return await couples.cancel(session, principal, request_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def end_couple(principal: CurrentUser, session: WriteSession) -> None:
    """End the couple (either partner, any time)."""
    await couples.end(session, principal)
