"""Other users: references, the couple picker and the choices of the user filters (CPL-01,
VIS-02, MEAL-10, UI-02)."""

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.repositories import users as users_repo
from app.schemas.users import SavedFilter, UserRef, VisibilityScope
from app.services import access
from app.services.principal import Principal


def user_ref(user: User) -> UserRef:
    return UserRef(id=user.id, display_name=user.display_name, deactivated=not user.is_active)


async def user_refs(session: AsyncSession, user_ids: Iterable[str | None]) -> dict[str, UserRef]:
    """References for the given ids; ids of deleted users are simply missing."""
    users = await users_repo.by_ids(session, (user_id for user_id in user_ids if user_id))
    return {user_id: user_ref(user) for user_id, user in users.items()}


async def hidden_by(session: AsyncSession, user_id: str, saved_filter: SavedFilter) -> set[str]:
    """What one of the user's saved filters hides (`FilterHidden`): the users unticked in the
    user filter on Meals (`meals`) or on Lists (`lists`), or the list states unticked in the state
    filter (`list_states`)."""
    user = await users_repo.get(session, user_id)
    return set() if user is None else set(user.filter_hidden.get(saved_filter, []))


async def list_others(session: AsyncSession, principal: Principal) -> list[UserRef]:
    """All active users except the caller, by display name (the couple picker)."""
    async with session.begin():
        return [
            user_ref(user) for user in await users_repo.active_except(session, principal.user_id)
        ]


async def list_visible(
    session: AsyncSession, principal: Principal, scope: VisibilityScope
) -> list[UserRef]:
    """The users whose meals (or lists) the caller can see, the choices of the user filter on
    Meals (or Lists): the caller first, their partner, then everyone else by display name.
    Deactivated users are included and flagged."""
    async with session.begin():
        partner = await access.partner_id(session, principal.user_id)
        owner_ids = await access.owners_visible_to(session, principal.user_id, partner, scope)
        users = await users_repo.by_ids(session, owner_ids)
    ordered = sorted(
        users.values(),
        key=lambda user: (user.id != principal.user_id, user.id != partner, user.display_name_norm),
    )
    return [user_ref(user) for user in ordered]
