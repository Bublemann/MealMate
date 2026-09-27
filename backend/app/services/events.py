"""The admin activity log (ADM-01, ADM-04)."""

from collections.abc import Mapping
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminEvent
from app.schemas.admin import AdminAction, AdminEventDetail


def record(
    session: AsyncSession,
    *,
    actor_id: str | None,
    action: AdminAction,
    target_user_id: str | None,
    now: datetime,
    details: Mapping[str, AdminEventDetail] | None = None,
) -> None:
    """Add a log entry to the caller's transaction; `actor_id` None means the command line."""
    session.add(
        AdminEvent(
            actor_id=actor_id,
            action=action.value,
            target_user_id=target_user_id,
            details=dict(details or {}),
            created_at=now,
        )
    )
