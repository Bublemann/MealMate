"""Queries on `users`."""

from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, user_id)


async def by_username_norm(session: AsyncSession, username_norm: str) -> User | None:
    result = await session.execute(select(User).where(User.username_norm == username_norm))
    return result.scalar_one_or_none()


async def username_taken(session: AsyncSession, username_norm: str) -> bool:
    return await by_username_norm(session, username_norm) is not None


async def display_name_taken(
    session: AsyncSession, display_name_norm: str, *, except_user_id: str | None = None
) -> bool:
    query = select(User.id).where(User.display_name_norm == display_name_norm)
    if except_user_id is not None:
        query = query.where(User.id != except_user_id)
    return (await session.execute(query)).first() is not None


async def by_ids(session: AsyncSession, user_ids: Iterable[str]) -> dict[str, User]:
    ids = {user_id for user_id in user_ids if user_id is not None}
    if not ids:
        return {}
    result = await session.execute(select(User).where(User.id.in_(ids)))
    return {user.id: user for user in result.scalars()}


async def all_by_display_name(session: AsyncSession) -> Sequence[User]:
    result = await session.execute(select(User).order_by(User.display_name_norm))
    return result.scalars().all()


async def active_except(session: AsyncSession, user_id: str) -> Sequence[User]:
    result = await session.execute(
        select(User)
        .where(User.is_active.is_(True), User.id != user_id)
        .order_by(User.display_name_norm)
    )
    return result.scalars().all()


async def any_exists(session: AsyncSession) -> bool:
    return (await session.execute(select(User.id).limit(1))).first() is not None


async def count_active_admins(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count()).where(User.role == "admin", User.is_active.is_(True))
    )
    return result.scalar_one()


async def with_public(session: AsyncSession, *, meals: bool) -> Sequence[User]:
    """Users whose meals (or lists) are public, deactivated ones included."""
    column = User.meals_public if meals else User.lists_public
    result = await session.execute(select(User).where(column.is_(True)))
    return result.scalars().all()

