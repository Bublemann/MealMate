"""Lifecycle hooks for data that later milestones add (plan § 6, deletion and lifecycle rules).

Meals (M4) and shopping lists (M5a) do not exist yet. The account rules already call these
hooks at the right point of their write transaction, so those milestones only fill them in.
Each hook runs inside the caller's transaction and must not commit.
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def on_couple_ended(session: AsyncSession, user_a_id: str, user_b_id: str) -> None:
    """Runs when a couple ends, before its rows are deleted (CPL-05).

    To be filled in:
    - M5a: set `shared_with_partner = false` on all lists of both users;
    - M4/M5a: detach each ex-partner's meals from the other's not-yet-frozen lists where they
      are no longer visible (LIST-15).
    """


async def on_meals_made_private(session: AsyncSession, user_id: str) -> None:
    """Runs when a user switches *meals public* off (VIS-02).

    To be filled in (M4/M5a): detach the owner's meals from not-yet-frozen lists owned by users
    who are neither the owner nor the partner.
    """


async def on_lists_made_private(session: AsyncSession, user_id: str) -> None:
    """Runs when a user switches *lists public* off (VIS-02).

    Visibility is computed on read, so nothing needs to change today; M5a may use this hook for
    derived data (e.g. cached list views of other users).
    """


async def before_user_deleted(session: AsyncSession, user_id: str) -> None:
    """Runs first when an admin deletes a user (ADM-03), before the couple ends.

    To be filled in:
    - M5a: move the lists they share with their partner to the partner (`owner_id` changes and
      `shared_with_partner` becomes false);
    - M4: detach their meals from every not-yet-frozen list they do not own, including the lists
      that just moved.
    Their own meals, remaining lists and sessions then go by `ON DELETE CASCADE`; media files
    are removed by the cleanup job (M8).
    """
