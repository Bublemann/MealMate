"""Admin section (ADM-01..04, ING-05, OPS-08). Every route needs an active admin."""

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import AppSettings, Config, CurrentAdmin, Now, limit_backup_requests
from app.db.session import ReadSession, WriteSession
from app.schemas.admin import (
    AdminEvent,
    AdminUser,
    AdminUserUpdate,
    Invite,
    InviteCreate,
    InviteCreated,
    LinkCreated,
    SystemInfo,
)
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.ingredients import Ingredient, IngredientMerge
from app.schemas.reference import Category, CategoryCreate, CategoryOrder, CategoryRename
from app.services import admin, codes, ingredients, reference, system

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


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def admin_create_category(
    body: CategoryCreate, principal: CurrentAdmin, session: WriteSession, now: Now
) -> Category:
    """Add a category with its German and English name; it goes last in the walking order. A
    name another category has in that language is a `taken` field error."""
    return await reference.create_category(session, principal, body.names, now=now)


@router.patch("/categories/{category_id}")
async def admin_rename_category(
    category_id: str, body: CategoryRename, principal: CurrentAdmin, session: WriteSession, now: Now
) -> Category:
    """Replace both names of a category, seeded ones included. A name another category has in
    that language is a `taken` field error."""
    return await reference.rename_category(session, principal, category_id, body.names, now=now)


@router.put("/categories/order")
async def admin_reorder_categories(
    body: CategoryOrder, principal: CurrentAdmin, session: WriteSession, now: Now
) -> list[Category]:
    """Set the category order to the shop's walking order; every category exactly once."""
    return await reference.reorder_categories(session, principal, body.category_ids, now=now)


@router.post("/ingredients/{ingredient_id}/merge")
async def admin_merge_ingredient(
    ingredient_id: str,
    body: IngredientMerge,
    principal: CurrentAdmin,
    session: WriteSession,
    now: Now,
) -> Ingredient:
    """Merge a duplicate into `into_id`: its references move there and it is deleted
    (ING-05). Returns the ingredient merged into."""
    return await ingredients.merge(session, principal, ingredient_id, body.into_id, now=now)


@router.delete(
    "/ingredients/{ingredient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def admin_delete_ingredient(
    ingredient_id: str, principal: CurrentAdmin, session: WriteSession, now: Now
) -> None:
    """Delete an ingredient that nothing refers to (409 `ingredient.in_use` otherwise)."""
    await ingredients.delete(session, principal, ingredient_id, now=now)


@router.get("/system")
async def admin_get_system(principal: CurrentAdmin, settings: AppSettings) -> SystemInfo:
    """The running version and the host's last backup and free disk space, as the host last
    wrote them to its read-only status files (null while there is none)."""
    return await system.system_info(settings)


@router.post(
    "/backup",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
    dependencies=[Depends(limit_backup_requests)],
    responses={
        status.HTTP_202_ACCEPTED: {"description": "Requested; the host starts the backup shortly"}
    },
)
async def admin_request_backup(
    principal: CurrentAdmin, session: WriteSession, settings: AppSettings, now: Now
) -> None:
    """Ask the host for a backup now (OPS-08), e.g. before an SD card swap; a request that is
    already waiting stays as it is. At most one request per minute (429)."""
    await system.request_backup(session, settings, principal, now=now)
