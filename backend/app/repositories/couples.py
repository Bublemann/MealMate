"""Queries on `couples` and `couple_members`."""

from collections.abc import Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Couple, CoupleMember


async def get(session: AsyncSession, couple_id: str) -> Couple | None:
    return await session.get(Couple, couple_id)


async def accepted_for(session: AsyncSession, user_id: str) -> Couple | None:
    """The user's couple, if they are in one."""
    result = await session.execute(
        select(Couple)
        .join(CoupleMember, CoupleMember.couple_id == Couple.id)
        .where(CoupleMember.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def pending_outgoing(session: AsyncSession, user_id: str) -> Couple | None:
    result = await session.execute(
        select(Couple).where(Couple.requester_id == user_id, Couple.status == "pending")
    )
    return result.scalars().first()


async def pending_incoming(session: AsyncSession, user_id: str) -> Sequence[Couple]:
    result = await session.execute(
        select(Couple)
        .where(Couple.addressee_id == user_id, Couple.status == "pending")
        .order_by(Couple.created_at, Couple.id)
    )
    return result.scalars().all()


async def pending_between(session: AsyncSession, user_a: str, user_b: str) -> Couple | None:
    result = await session.execute(
        select(Couple).where(
            Couple.status == "pending",
            or_(
                (Couple.requester_id == user_a) & (Couple.addressee_id == user_b),
                (Couple.requester_id == user_b) & (Couple.addressee_id == user_a),
            ),
        )
    )
    return result.scalars().first()


async def delete_pending_involving(session: AsyncSession, *user_ids: str) -> None:
    """Cancel every pending request sent by or to any of `user_ids`."""
    await session.execute(
        delete(Couple).where(
            Couple.status == "pending",
            or_(Couple.requester_id.in_(user_ids), Couple.addressee_id.in_(user_ids)),
        )
    )


def add_members(session: AsyncSession, couple: Couple) -> None:
    session.add_all(
        [
            CoupleMember(user_id=couple.requester_id, couple_id=couple.id),
            CoupleMember(user_id=couple.addressee_id, couple_id=couple.id),
        ]
    )


async def delete_couple(session: AsyncSession, couple: Couple) -> None:
    await session.execute(delete(CoupleMember).where(CoupleMember.couple_id == couple.id))
    await session.execute(delete(Couple).where(Couple.id == couple.id))
