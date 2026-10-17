"""Notices (D-51): each is for one user and stays unread until that user dismisses it.

The lifecycle hooks write them (`services.hooks`), so this module must not import
`services.ingredients` or anything else that imports the hooks.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notice as NoticeRow
from app.repositories import notices as notices_repo
from app.schemas.notices import Notice, NoticeKind, NoticeList
from app.services import access
from app.services.principal import Principal


def _view(row: NoticeRow) -> Notice:
    return Notice(
        id=row.id, kind=cast(NoticeKind, row.kind), params=row.params, created_at=row.created_at
    )


def notify(
    session: AsyncSession,
    user_ids: Iterable[str],
    kind: NoticeKind,
    params: dict[str, str | None],
    *,
    now: datetime,
) -> None:
    """Leave each user an unread notice of `kind`, inside the caller's transaction."""
    session.add_all(
        NoticeRow(user_id=user_id, kind=kind, params=dict(params), created_at=now)
        for user_id in user_ids
    )


async def list_unread(session: AsyncSession, principal: Principal) -> NoticeList:
    """The caller's unread notices, newest first."""
    async with session.begin():
        rows = await notices_repo.unread_of(session, principal.user_id)
    return NoticeList(notices=[_view(row) for row in rows], count=len(rows))


async def dismiss(
    session: AsyncSession, principal: Principal, notice_id: str, *, now: datetime
) -> None:
    """The caller has read one of their notices; it stays read when dismissed again. Each
    partner dismisses their own."""
    async with session.begin():
        notice = await access.require_own_notice(session, principal, notice_id)
        if notice.dismissed_at is None:
            notice.dismissed_at = now
