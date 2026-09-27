"""The own account (ACC-09, ACC-10, ACC-13, VIS-02, I18N-01)."""

from fastapi import APIRouter, Response, status

from app.api.deps import Config, CurrentUser, Now
from app.db.session import ReadSession, WriteSession
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.users import Me, MeUpdate, PasswordChange, SecurityInfo, SessionInfo
from app.services import me

router = APIRouter(prefix="/api/me", tags=["me"], responses=ERROR_RESPONSES)


@router.get("")
async def get_me(principal: CurrentUser, session: ReadSession) -> Me:
    """The own profile and settings."""
    return await me.get_me(session, principal)


@router.patch("")
async def update_me(body: MeUpdate, principal: CurrentUser, session: WriteSession, now: Now) -> Me:
    """Change display name, language, privacy switches or hidden filter chips."""
    return await me.update_me(session, principal, body, now=now)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def change_password(
    body: PasswordChange, principal: CurrentUser, session: WriteSession, config: Config, now: Now
) -> None:
    """Change the password; logs out all other devices."""
    await me.change_password(
        session,
        config,
        principal,
        current_password=body.current_password,
        new_password=body.new_password,
        now=now,
    )


@router.get("/sessions")
async def list_sessions(
    principal: CurrentUser, session: ReadSession, now: Now
) -> list[SessionInfo]:
    """The own logged-in devices, most recently used first."""
    return await me.list_sessions(session, principal, now=now)


@router.delete(
    "/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def revoke_session(
    session_id: str, principal: CurrentUser, session: WriteSession, now: Now
) -> None:
    """Log out one of the own devices."""
    await me.revoke_session(session, principal, session_id, now=now)


@router.get("/security")
async def get_security(principal: CurrentUser, session: ReadSession) -> SecurityInfo:
    """Password change and reset notices ("Password reset by X on <date>")."""
    return await me.security_info(session, principal)
