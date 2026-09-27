"""Admin section (ADM-01..04). Every route needs an active admin."""

from fastapi import APIRouter, Response, status

from app.api.deps import Config, CurrentAdmin, Now
from app.db.session import ReadSession, WriteSession
from app.schemas.admin import (
    AdminEvent,
    AdminUser,
    AdminUserUpdate,
    Invite,
    InviteCreate,
    InviteCreated,
    LinkCreated,
)
from app.schemas.errors import ERROR_RESPONSES
from app.services import admin, codes

router = APIRouter(prefix="/api/admin", tags=["admin"], responses=ERROR_RESPONSES)


@router.get("/users")
async def admin_list_users(principal: CurrentAdmin, session: ReadSession) -> list[AdminUser]:
    """All users, by display name."""
    return await admin.list_users(session)


@router.patch("/users/{user_id}")
async def admin_update_user(
    user_id: str, body: AdminUserUpdate, principal: CurrentAdmin, session: WriteSession, now: Now
) -> AdminUser:
    """Change another user's role or deactivate/reactivate them."""
    return await admin.update_user(session, principal, user_id, body, now=now)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def admin_delete_user(
    user_id: str, principal: CurrentAdmin, session: WriteSession, now: Now
) -> None:
    """Delete another user and their data (ADM-03)."""
    await admin.delete_user(session, principal, user_id, now=now)


@router.post("/users/{user_id}/reset-link")
async def admin_create_reset_link(
    user_id: str, principal: CurrentAdmin, session: WriteSession, config: Config, now: Now
) -> LinkCreated:
    """A single-use password reset link for the user (ACC-10); older ones stop working."""
    return await codes.create_reset_link(
        session, config, actor_id=principal.user_id, user_id=user_id, now=now
    )


@router.get("/invites")
async def admin_list_invites(
    principal: CurrentAdmin, session: ReadSession, now: Now
) -> list[Invite]:
    """All invites with their status, newest first."""
    return await codes.list_invites(session, now=now)


@router.post("/invites", status_code=status.HTTP_201_CREATED)
async def admin_create_invite(
    body: InviteCreate, principal: CurrentAdmin, session: WriteSession, config: Config, now: Now
) -> InviteCreated:
    """A new invite link (ACC-02); the link is returned only this once."""
    return await codes.create_invite(
        session,
        config,
        actor_id=principal.user_id,
        tailscale_share_url=body.tailscale_share_url,
        now=now,
    )


@router.delete(
    "/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def admin_revoke_invite(
    invite_id: str, principal: CurrentAdmin, session: WriteSession, now: Now
) -> None:
    """Revoke an invite so it can no longer be used."""
    await codes.revoke_invite(session, actor_id=principal.user_id, invite_id=invite_id, now=now)


@router.get("/events")
async def admin_list_events(principal: CurrentAdmin, session: ReadSession) -> list[AdminEvent]:
    """The admin activity log, newest first (at most 200 entries)."""
    return await admin.list_events(session)
