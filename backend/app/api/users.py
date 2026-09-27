"""Other users: the couple picker and the user filter chips (CPL-01, VIS-02)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser
from app.db.session import ReadSession
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.users import UserRef, VisibilityScope
from app.services import users

router = APIRouter(prefix="/api/users", tags=["users"], responses=ERROR_RESPONSES)


@router.get("")
async def list_users(principal: CurrentUser, session: ReadSession) -> list[UserRef]:
    """All active users except yourself, by display name."""
    return await users.list_others(session, principal)


@router.get("/visible")
async def list_visible_users(
    principal: CurrentUser,
    session: ReadSession,
    scope: Annotated[VisibilityScope, Query(alias="for")],
) -> list[UserRef]:
    """Users whose meals (`for=meals`) or lists (`for=lists`) you can see: yourself first,
    your partner, and everyone whose matching privacy switch is public."""
    return await users.list_visible(session, principal, scope)
