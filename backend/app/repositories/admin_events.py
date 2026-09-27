"""Queries on `admin_events`."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminEvent


async def newest(session: AsyncSession, limit: int) -> Sequence[AdminEvent]:
    result = await session.execute(
        select(AdminEvent).order_by(AdminEvent.created_at.desc(), AdminEvent.id.desc()).limit(limit)
    )
    return result.scalars().all()
