"""All permission checks in one place (plan § 5.5, SEC-04).

| Object | View | Edit |
|---|---|---|
| Own account, couple | self | self |
| Meal (M4) | owner · partner · everyone if *meals public* (VIS-02, CPL-04) | owner (VIS-04) |
| Meal photo (M4) | as its meal; signed URLs only after the view check (VIS-05) | owner |
| List (M5a) | owner · partner (CPL-04) · all if *lists public* | owner · partner if shared |
| Meal on a list (M5a) | details if its meal is visible, else "Private meal" (VIS-06) | n/a |
| Ingredient, product (M3) | everyone | everyone; merge and delete: admin (ING-01, ING-05) |
| Reference data (M3) | everyone | add a cuisine: everyone; reorder categories: admin |
| Admin endpoints | active admin (`require_admin`) | same; never self-deactivation or deletion |

A list's partner sees it while the couple exists; everyone but the owner (and the partner of a
shared list) sees it read-only. Only the owner deletes a list and switches sharing (LIST-13).

Ingredients and products are a shared household wiki, so they need no per-object check; the
admin-only actions go through `require_admin` (via the `CurrentAdmin` dependency).

A meal or list the viewer may not see answers exactly like one that does not exist (404
`common.not_found`), so its existence never leaks; a visible meal or list the viewer may not
change answers edits with 403 `common.forbidden`.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode, not_found
from app.models import Meal, ShoppingList
from app.repositories import couples as couples_repo
from app.repositories import lists as lists_repo
from app.repositories import meals as meals_repo
from app.repositories import users as users_repo
from app.schemas.users import VisibilityScope
from app.services.principal import Principal


def _forbidden() -> ApiError:
    return ApiError(ErrorCode.FORBIDDEN, status_code=403)


def require_admin(principal: Principal) -> None:
    """Admin endpoints: active admins only (the principal is active by construction)."""
    if not principal.is_admin:
        raise _forbidden()


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


async def may_view_meals_of(session: AsyncSession, viewer_id: str, owner_id: str) -> bool:
    """Whether the viewer may see the meals of `owner_id` (VIS-01/02, CPL-04)."""
    return owner_id == viewer_id or owner_id in await visible_owner_ids(session, viewer_id, "meals")


async def require_meal_view(session: AsyncSession, principal: Principal, meal_id: str) -> Meal:
    """The meal, if the principal may see it; 404 `common.not_found` otherwise, exactly as for
    a meal that does not exist."""
    meal = await meals_repo.get(session, meal_id)
    if meal is None or not await may_view_meals_of(session, principal.user_id, meal.owner_id):
        raise not_found()
    return meal


async def require_meal_owner(session: AsyncSession, principal: Principal, meal_id: str) -> Meal:
    """The meal, if the principal owns it (MEAL-07, VIS-04): 404 if they may not even see it,
    403 `common.forbidden` if it is someone else's visible meal."""
    meal = await require_meal_view(session, principal, meal_id)
    if meal.owner_id != principal.user_id:
        raise _forbidden()
    return meal


@dataclass(frozen=True)
class ListRights:
    """What a viewer may do with a list they can see (CPL-02/03, VIS-03)."""

    is_owner: bool
    can_edit: bool


def list_rights(
    viewer_id: str, viewer_partner_id: str | None, shopping_list: ShoppingList, owner_public: bool
) -> ListRights | None:
    """The viewer's rights on a list, or None if they may not see it: the owner edits; the
    owner's partner sees every list while the couple exists and edits the shared ones
    (CPL-02/04); everyone else only sees the lists of owners whose *lists public* switch is on
    (VIS-02/03)."""
    if shopping_list.owner_id == viewer_id:
        return ListRights(is_owner=True, can_edit=True)
    if shopping_list.owner_id == viewer_partner_id:
        return ListRights(is_owner=False, can_edit=shopping_list.shared_with_partner)
    if owner_public:
        return ListRights(is_owner=False, can_edit=False)
    return None


async def require_list_view(
    session: AsyncSession, principal: Principal, list_id: str
) -> tuple[ShoppingList, ListRights]:
    """The list and the principal's rights on it; 404 `common.not_found` if they may not see
    it, exactly as for a list that does not exist."""
    shopping_list = await lists_repo.get(session, list_id)
    if shopping_list is None:
        raise not_found()
    owner = await users_repo.get(session, shopping_list.owner_id)
    rights = list_rights(
        principal.user_id,
        await partner_id(session, principal.user_id),
        shopping_list,
        owner_public=owner is not None and owner.lists_public,
    )
    if rights is None:
        raise not_found()
    return shopping_list, rights


async def require_list_edit(
    session: AsyncSession, principal: Principal, list_id: str
) -> tuple[ShoppingList, ListRights]:
    """The list, if the principal may change it (CPL-03): 404 if they may not even see it,
    403 `common.forbidden` if they only see it."""
    shopping_list, rights = await require_list_view(session, principal, list_id)
    if not rights.can_edit:
        raise _forbidden()
    return shopping_list, rights


async def require_list_owner(
    session: AsyncSession, principal: Principal, list_id: str
) -> tuple[ShoppingList, ListRights]:
    """The list, if the principal owns it (delete, share switch; LIST-13, CPL-02): 404 if
    they may not even see it, 403 `common.forbidden` otherwise."""
    shopping_list, rights = await require_list_view(session, principal, list_id)
    if not rights.is_owner:
        raise _forbidden()
    return shopping_list, rights
