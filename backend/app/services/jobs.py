"""Background jobs behind `mealmate jobs ...` (plan § 5.11), run by systemd timers (M8).

`cleanup` removes orphaned media files: photos no meal refers to any more (a replaced or deleted
photo whose best-effort deletion failed, a deleted user's meals, a copy or upload whose
transaction failed). M8 adds expired codes, tokens and processed ops.
"""

from functools import partial

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.media.store import MediaStore
from app.repositories import meals as meals_repo


async def cleanup(session: AsyncSession, media: MediaStore, *, now: float) -> int:
    """Delete media files that no meal refers to and that are older than an hour (so uploads
    and copies still waiting for their transaction are kept); returns how many were deleted.
    `now` is Unix time, compared with the files' modification times."""
    async with session.begin():
        referenced = await meals_repo.photo_keys(session)
    return await anyio.to_thread.run_sync(partial(media.remove_orphans, referenced, now=now))
