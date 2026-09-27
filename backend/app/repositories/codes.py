"""Queries on `one_time_codes` (invites and reset links)."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OneTimeCode


async def by_hmac(session: AsyncSession, code_hmac: str) -> OneTimeCode | None:
    result = await session.execute(select(OneTimeCode).where(OneTimeCode.code_hmac == code_hmac))
    return result.scalar_one_or_none()


async def get(session: AsyncSession, code_id: str) -> OneTimeCode | None:
    return await session.get(OneTimeCode, code_id)


async def invites_newest_first(session: AsyncSession) -> Sequence[OneTimeCode]:
    result = await session.execute(
        select(OneTimeCode)
        .where(OneTimeCode.kind == "invite")
        .order_by(OneTimeCode.created_at.desc(), OneTimeCode.id.desc())
    )
    return result.scalars().all()


async def revoke_open_resets(session: AsyncSession, user_id: str, now: datetime) -> None:
    """Revoke the user's reset links that could still be used."""
    await session.execute(
        update(OneTimeCode)
        .where(
            OneTimeCode.kind == "reset",
            OneTimeCode.target_user_id == user_id,
            OneTimeCode.used_at.is_(None),
            OneTimeCode.revoked_at.is_(None),
            OneTimeCode.expires_at > now,
        )
        .values(revoked_at=now)
    )


async def delete_finished_before(session: AsyncSession, cutoff: datetime) -> int:
    """Delete codes that expired, were used or were revoked before `cutoff`; returns how many."""
    deleted = await session.scalars(
        delete(OneTimeCode)
        .where(
            or_(
                OneTimeCode.expires_at < cutoff,
                OneTimeCode.used_at < cutoff,
                OneTimeCode.revoked_at < cutoff,
            )
        )
        .returning(OneTimeCode.id)
    )
    return len(deleted.all())
