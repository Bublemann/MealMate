"""Background jobs behind `mealmate jobs ...` (plan § 5.11), run by systemd timers (M8).

`cleanup` (daily) removes what nothing needs any more:
- orphaned media files: photos no meal refers to any more (a replaced or deleted photo whose
  best-effort deletion failed, a deleted user's meals, a copy or upload whose transaction
  failed), once they are an hour old;
- invites and reset links that expired, were used or were revoked more than 30 days ago (the
  admin page lists invites until then);
- refresh tokens that expired more than a day ago, and sessions revoked or idle-expired more
  than 30 days ago (their tokens go with them);
- processed shopping ops applied more than 30 days ago (plan § 5.8).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.store import MediaStore
from app.repositories import codes as codes_repo
from app.repositories import lists as lists_repo
from app.repositories import meals as meals_repo
from app.repositories import sessions as sessions_repo

CODE_RETENTION = timedelta(days=30)
TOKEN_RETENTION = timedelta(days=1)
SESSION_RETENTION = timedelta(days=30)
PROCESSED_OP_RETENTION = timedelta(days=30)


@dataclass(frozen=True)
class CleanupResult:
    """How many of each were deleted."""

    media_files: int
    codes: int
    session_tokens: int
    sessions: int
    processed_ops: int


async def cleanup(session: AsyncSession, media: MediaStore, *, now: datetime) -> CleanupResult:
    """Delete what is no longer needed (see above). Media files count by their modification
    time, so uploads and copies still waiting for their transaction are kept."""
    async with session.begin():
        codes = await codes_repo.delete_finished_before(session, now - CODE_RETENTION)
        # Tokens first, so the count doesn't include the tokens of deleted sessions.
        tokens = await sessions_repo.delete_tokens_expired_before(session, now - TOKEN_RETENTION)
        sessions = await sessions_repo.delete_ended_before(session, now - SESSION_RETENTION)
        ops = await lists_repo.delete_processed_ops_before(session, now - PROCESSED_OP_RETENTION)
        referenced = await meals_repo.photo_keys(session)
    media_files = await anyio.to_thread.run_sync(
        partial(media.remove_orphans, referenced, now=now.timestamp())
    )
    return CleanupResult(
        media_files=media_files,
        codes=codes,
        session_tokens=tokens,
        sessions=sessions,
        processed_ops=ops,
    )
