"""All permission checks in one place (plan § 5.5, SEC-04).

M2 has users, couples and the admin section; meals and lists add their rules here in M4/M5a.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode
from app.repositories import couples as couples_repo
from app.repositories import users as users_repo
from app.schemas.users import VisibilityScope
from app.services.principal import Principal


def require_admin(principal: Principal) -> None:
    """Admin endpoints: active admins only (the principal is active by construction)."""
    if not principal.is_admin:
        raise ApiError(ErrorCode.FORBIDDEN, status_code=403)


async def partner_id(session: AsyncSession, user_id: str) -> str | None:
    """The user's partner while the couple exists (deactivated partners included, CPL-07)."""
    couple = await couples_repo.accepted_for(session, user_id)
    if couple is None:
        return None
    return couple.addressee_id if couple.requester_id == user_id else couple.requester_id


async def visible_owner_ids(
    session: AsyncSession, viewer_id: str, scope: VisibilityScope
) -> set[str]:
    """Whose meals (or lists) the viewer may see: their own, their partner's (always, CPL-04),
    and those of users whose *meals public* (*lists public*) switch is on (VIS-02)."""
    owners = {viewer_id}
    if (partner := await partner_id(session, viewer_id)) is not None:
        owners.add(partner)
    owners.update(user.id for user in await users_repo.with_public(session, meals=scope == "meals"))
    return owners
