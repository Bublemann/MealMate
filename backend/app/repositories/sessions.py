"""Queries on `sessions` and `session_tokens`."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthSession, SessionToken, User


async def with_user(session: AsyncSession, session_id: str) -> tuple[AuthSession, User] | None:
    """The session and its user in one indexed lookup (the per-request check)."""
    result = await session.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.id == session_id)
    )
    row = result.first()
    return None if row is None else (row[0], row[1])


async def get(session: AsyncSession, session_id: str) -> AuthSession | None:
    return await session.get(AuthSession, session_id)


async def token_by_hmac(
    session: AsyncSession, token_hmac: str
) -> tuple[SessionToken, AuthSession, User] | None:
    result = await session.execute(
        select(SessionToken, AuthSession, User)
        .join(AuthSession, AuthSession.id == SessionToken.session_id)
        .join(User, User.id == AuthSession.user_id)
        .where(SessionToken.token_hmac == token_hmac)
    )
    row = result.first()
    return None if row is None else (row[0], row[1], row[2])


async def supersede_active_tokens(session: AsyncSession, session_id: str, now: datetime) -> None:
    """Mark every still-active token of the session superseded (the presented one and any
    leftover grace siblings)."""
    await session.execute(
        update(SessionToken)
        .where(SessionToken.session_id == session_id, SessionToken.superseded_at.is_(None))
        .values(superseded_at=now)
    )


async def live_for_user(
    session: AsyncSession, user_id: str, now: datetime
) -> Sequence[AuthSession]:
    """Sessions that are neither revoked nor idle-expired, most recently used first."""
    result = await session.execute(
        select(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .order_by(AuthSession.last_used_at.desc(), AuthSession.id.desc())
    )
    return result.scalars().all()


async def revoke_for_user(
    session: AsyncSession, user_id: str, now: datetime, *, except_session_id: str | None = None
) -> None:
    query = update(AuthSession).where(
        AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
    )
    if except_session_id is not None:
        query = query.where(AuthSession.id != except_session_id)
    await session.execute(query.values(revoked_at=now))


async def revoke_family(session: AsyncSession, auth_session: AuthSession, now: datetime) -> None:
    """Revoke `auth_session` and every session linked to it by forks: the one it was forked
    from, those forked from it, and so on (a household device has at most a few)."""
    family = {auth_session.id}
    frontier = {auth_session.id}
    while frontier:
        linked = await session.scalars(
            select(AuthSession.id).where(
                AuthSession.user_id == auth_session.user_id,
                or_(
                    AuthSession.id.in_(
                        select(AuthSession.parent_session_id).where(AuthSession.id.in_(frontier))
                    ),
                    AuthSession.parent_session_id.in_(frontier),
                ),
            )
        )
        frontier = set(linked) - family
        family |= frontier
    await session.execute(
        update(AuthSession)
        .where(AuthSession.id.in_(family), AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def delete_tokens_expired_before(session: AsyncSession, cutoff: datetime) -> int:
    """Delete refresh tokens that expired before `cutoff`; returns how many."""
    deleted = await session.scalars(
        delete(SessionToken).where(SessionToken.expires_at < cutoff).returning(SessionToken.id)
    )
    return len(deleted.all())


async def delete_ended_before(session: AsyncSession, cutoff: datetime) -> int:
    """Delete sessions revoked or idle-expired before `cutoff` (their tokens go with them);
    returns how many."""
    deleted = await session.scalars(
        delete(AuthSession)
        .where(or_(AuthSession.revoked_at < cutoff, AuthSession.expires_at < cutoff))
        .returning(AuthSession.id)
    )
    return len(deleted.all())
