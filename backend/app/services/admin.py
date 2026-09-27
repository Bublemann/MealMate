"""Admin section: users, roles, deactivation, deletion and the activity log (ADM-01..04).

Admins never see other users' meals or lists here (ADM-04). They cannot change or delete
themselves, and at least one active admin always remains.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode, not_found
from app.models import User
from app.repositories import admin_events as events_repo
from app.repositories import couples as couples_repo
from app.repositories import sessions as sessions_repo
from app.repositories import users as users_repo
from app.schemas.admin import AdminAction, AdminEvent, AdminUser, AdminUserUpdate
from app.services import couples, events, hooks
from app.services.principal import Principal
from app.services.users import user_refs

EVENTS_LIMIT = 200


def _conflict(code: ErrorCode) -> ApiError:
    return ApiError(code, status_code=409)


def admin_user(user: User) -> AdminUser:
    return AdminUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role="admin" if user.role == "admin" else "user",
        is_active=user.is_active,
        created_at=user.created_at,
        last_seen_at=user.last_seen_at,
    )


async def ensure_an_active_admin_remains(session: AsyncSession) -> None:
    """Raise 409 `admin.last_admin` if the pending changes leave no active admin."""
    if await users_repo.count_active_admins(session) == 0:
        raise _conflict(ErrorCode.ADMIN_LAST_ADMIN)


async def _target(session: AsyncSession, actor: Principal, user_id: str) -> User:
    if user_id == actor.user_id:
        raise _conflict(ErrorCode.ADMIN_SELF_FORBIDDEN)
    user = await users_repo.get(session, user_id)
    if user is None:
        raise not_found()
    return user


async def list_users(session: AsyncSession) -> list[AdminUser]:
    async with session.begin():
        return [admin_user(user) for user in await users_repo.all_by_display_name(session)]


async def deactivate(session: AsyncSession, user: User, *, now: datetime) -> None:
    """Block the user at once (ADM-02): end their sessions and cancel their pending couple
    requests. Their couple and data stay (CPL-07)."""
    user.is_active = False
    await sessions_repo.revoke_for_user(session, user.id, now)
    await couples_repo.delete_pending_involving(session, user.id)


async def update_user(
    session: AsyncSession,
    actor: Principal,
    user_id: str,
    update: AdminUserUpdate,
    *,
    now: datetime,
) -> AdminUser:
    """Promote or demote, deactivate or reactivate another user; each change is logged."""
    async with session.begin():
        user = await _target(session, actor, user_id)
        if update.role is not None and update.role != user.role:
            events.record(
                session,
                actor_id=actor.user_id,
                action=AdminAction.USER_ROLE_CHANGE,
                target_user_id=user.id,
                now=now,
                details={"from": user.role, "to": update.role},
            )
            user.role = update.role
        if update.is_active is not None and update.is_active != user.is_active:
            if update.is_active:
                user.is_active = True
                action = AdminAction.USER_REACTIVATE
            else:
                await deactivate(session, user, now=now)
                action = AdminAction.USER_DEACTIVATE
            events.record(
                session, actor_id=actor.user_id, action=action, target_user_id=user.id, now=now
            )
        user.updated_at = now
        await session.flush()
        await ensure_an_active_admin_remains(session)
        return admin_user(user)


async def delete_user(
    session: AsyncSession, actor: Principal, user_id: str, *, now: datetime
) -> None:
    """Delete another user (ADM-03) in one transaction: the hook for their lists and meals
    (M4/M5a), then their couple ends, then everything of theirs goes by `ON DELETE CASCADE`
    (sessions, reset links, couple requests). What others refer to (log entries, invites they
    created or used) keeps its row with the reference set to NULL ("deleted user")."""
    async with session.begin():
        user = await _target(session, actor, user_id)
        await hooks.before_user_deleted(session, user.id)
        if (couple := await couples_repo.accepted_for(session, user.id)) is not None:
            await couples.end_couple(session, couple)
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.USER_DELETE,
            target_user_id=None,
            now=now,
            details={"display_name": user.display_name},
        )
        await session.delete(user)
        await session.flush()
        await ensure_an_active_admin_remains(session)


async def list_events(session: AsyncSession) -> list[AdminEvent]:
    """The newest 200 log entries, newest first."""
    async with session.begin():
        rows = await events_repo.newest(session, EVENTS_LIMIT)
        refs = await user_refs(
            session, [user_id for row in rows for user_id in (row.actor_id, row.target_user_id)]
        )
    return [
        AdminEvent(
            id=row.id,
            actor=refs.get(row.actor_id) if row.actor_id else None,
            action=AdminAction(row.action),
            target=refs.get(row.target_user_id) if row.target_user_id else None,
            details=row.details,
            created_at=row.created_at,
        )
        for row in rows
    ]
