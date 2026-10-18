"""Queries on `notices`."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notice


async def get(session: AsyncSession, notice_id: str) -> Notice | None:
    return await session.get(Notice, notice_id)


async def unread_of(session: AsyncSession, user_id: str) -> Sequence[Notice]:
    """The user's notices they haven't dismissed, newest first."""
    result = await session.execute(
        select(Notice)
        .where(Notice.user_id == user_id, Notice.dismissed_at.is_(None))
        .order_by(Notice.created_at.desc(), Notice.id.desc())
    )
    return result.scalars().all()
