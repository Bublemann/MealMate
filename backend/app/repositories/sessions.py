"""Queries on `sessions` and `session_tokens`."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
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
