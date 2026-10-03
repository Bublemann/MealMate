"""Reference data: categories and their order, units, cuisines, tags (REF-01..04, ADM-01)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ApiError,
    ErrorCode,
    FieldErrorCode,
    FieldProblem,
    not_found,
    validation_error,
)
from app.domain.reference import CUISINE_KEYS, OTHER_CATEGORY, UNCATEGORIZED_CATEGORY
from app.domain.text import normalize
from app.domain.units import UNIT_KIND, Unit
from app.models import Category as CategoryRow
from app.models import Cuisine as CuisineRow
from app.repositories import ingredients as ingredients_repo
from app.repositories import lists as lists_repo
from app.repositories import reference as reference_repo
from app.schemas.admin import AdminAction, AdminEventDetail
from app.schemas.reference import (
    Category,
    CategoryNames,
    CategoryUsage,
    Cuisine,
    Tag,
    UnitInfo,
)
from app.services import events
from app.services.principal import Principal

TAGS_LIMIT = 20
_CUISINE_POSITION = {key: position for position, key in enumerate(CUISINE_KEYS)}


def category(row: CategoryRow) -> Category:
    return Category(
        id=row.id,
        key=row.key,
        names=CategoryNames(de=row.name_de, en=row.name_en),
        sort_order=row.sort_order,
        deleted=row.deleted_at is not None,
    )


def cuisine(row: CuisineRow) -> Cuisine:
    return Cuisine(id=row.id, key=row.key, name=row.name)


def _cuisine_order(row: CuisineRow) -> tuple[int, int, str]:
    """Seeded cuisines in seed order (unknown future keys after them), then the rest by name."""
    if row.key is not None:
        return (0, _CUISINE_POSITION.get(row.key, len(CUISINE_KEYS)), row.key)
    return (1, 0, row.name_norm)


async def list_categories(session: AsyncSession) -> list[Category]:
    """Every category, deleted ones included (D-30), in order."""
    async with session.begin():
        return [category(row) for row in await reference_repo.categories_in_order(session)]


async def pickable_category(session: AsyncSession, category_id: str) -> CategoryRow | None:
    """The category, if new ingredients and free-text items may go into it (ING-02, LIST-06):
    not a deleted one (D-30), nor *Uncategorized*, where nothing is put on purpose."""
    row = await reference_repo.get_category(session, category_id)
    if row is None or row.deleted_at is not None or row.key == UNCATEGORIZED_CATEGORY:
        return None
    return row


def _shown(rows: Sequence[CategoryRow]) -> list[CategoryRow]:
    """The categories that aren't deleted: the walking order admins see and change."""
    return [row for row in rows if row.deleted_at is None]


def _find(rows: Sequence[CategoryRow], category_id: str) -> CategoryRow:
    """A category that isn't deleted; a deleted one can't be changed any more (404, D-30)."""
    row = next((row for row in _shown(rows) if row.id == category_id), None)
    if row is None:
        raise not_found()
    return row


def list_units() -> list[UnitInfo]:
    """Every unit, in display order."""
    return [UnitInfo(unit=unit, kind=UNIT_KIND[unit]) for unit in Unit]


async def list_cuisines(session: AsyncSession) -> list[Cuisine]:
    async with session.begin():
        rows = await reference_repo.all_cuisines(session)
    return [cuisine(row) for row in sorted(rows, key=_cuisine_order)]


@dataclass(frozen=True)
class CuisineResult:
    cuisine: Cuisine
    created: bool


async def create_cuisine(
    session: AsyncSession, principal: Principal, name: str, *, now: datetime
) -> CuisineResult:
    """Add a cuisine as plain text (REF-03), or return the existing one with the same
    normalised name; a seeded cuisine matches by its key."""
    name_norm = normalize(name)
    async with session.begin():
        existing = await reference_repo.cuisine_by_name_norm(session, name_norm)
        if existing is not None:
            return CuisineResult(cuisine(existing), created=False)
        row = CuisineRow(
            key=None,
            name=name,
            name_norm=name_norm,
            created_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        return CuisineResult(cuisine(row), created=True)


async def list_tags(session: AsyncSession, query: str | None) -> list[Tag]:
    """At most 20 tags matching the query (normalised), prefix matches first (REF-04)."""
    async with session.begin():
        rows = await reference_repo.tags_matching(session, normalize(query or ""), TAGS_LIMIT)
    return [Tag(id=row.id, name=row.name) for row in rows]


async def reorder_categories(
    session: AsyncSession, actor: Principal, category_ids: list[str], *, now: datetime
) -> list[Category]:
    """Admins set the shop's walking order (ADM-01): `category_ids` must name every category
    that isn't deleted exactly once, *Uncategorized* included; their `sort_order` becomes 0..n-1
    in that order. Returns every category, as `list_categories` does."""
    async with session.begin():
        rows = await reference_repo.categories_in_order(session)
        by_id = {row.id: row for row in _shown(rows)}
        if len(category_ids) != len(by_id) or set(category_ids) != set(by_id):
            raise validation_error([FieldProblem(("body", "category_ids"), FieldErrorCode.INVALID)])
        for position, category_id in enumerate(category_ids):
            row = by_id[category_id]
            if row.sort_order != position:
                row.sort_order = position
                row.updated_at = now
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.CATEGORY_REORDER,
            target_user_id=None,
            now=now,
        )
        await session.flush()
        return [category(row) for row in await reference_repo.categories_in_order(session)]


def _taken_names(
    categories: Sequence[CategoryRow], names: CategoryNames, *, own_id: str | None = None
) -> list[FieldProblem]:
    """A field error for each name another category that isn't deleted has in the same
    language, ignoring case, umlauts and accents (REF-01). A category's own names are never
    taken, and a deleted one's can be used again."""
    others = [row for row in _shown(categories) if row.id != own_id]
    taken = []
    if normalize(names.de) in {row.name_de_norm for row in others}:
        taken.append(FieldProblem(("body", "names", "de"), FieldErrorCode.TAKEN))
    if normalize(names.en) in {row.name_en_norm for row in others}:
        taken.append(FieldProblem(("body", "names", "en"), FieldErrorCode.TAKEN))
    return taken


def _set_names(row: CategoryRow, names: CategoryNames) -> None:
    row.name_de, row.name_de_norm = names.de, normalize(names.de)
    row.name_en, row.name_en_norm = names.en, normalize(names.en)


def _name_details(names: CategoryNames, prefix: str = "") -> dict[str, AdminEventDetail]:
    """The names for the activity log, which shows them in the UI language."""
    return {f"{prefix}name_de": names.de, f"{prefix}name_en": names.en}


async def create_category(
    session: AsyncSession, actor: Principal, names: CategoryNames, *, now: datetime
) -> Category:
    """Admins add a category with both names (REF-01); it has no key and goes last in the
    walking order."""
    async with session.begin():
        rows = await reference_repo.categories_in_order(session)
        taken = _taken_names(rows, names)
        if taken:
            raise validation_error(taken)
        row = CategoryRow(key=None, sort_order=len(_shown(rows)), created_at=now, updated_at=now)
        _set_names(row, names)
        session.add(row)
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.CATEGORY_CREATE,
            target_user_id=None,
            now=now,
            details=_name_details(names),
        )
        await session.flush()
        return category(row)


async def rename_category(
    session: AsyncSession,
    actor: Principal,
    category_id: str,
    names: CategoryNames,
    *,
    now: datetime,
) -> Category:
    """Admins replace both names of any category, seeded ones included, except *Uncategorized*
    (409 `category.not_renamable`, REF-01). The new names show on every list, old ones included,
    because lists refer to the category. A rename that changes nothing logs nothing."""
    async with session.begin():
        rows = await reference_repo.categories_in_order(session)
        row = _find(rows, category_id)
        if row.key == UNCATEGORIZED_CATEGORY:
            raise ApiError(ErrorCode.CATEGORY_NOT_RENAMABLE, status_code=409)
        taken = _taken_names(rows, names, own_id=row.id)
        if taken:
            raise validation_error(taken)
        old = category(row).names
        if names != old:
            _set_names(row, names)
            row.updated_at = now
            events.record(
                session,
                actor_id=actor.user_id,
                action=AdminAction.CATEGORY_RENAME,
                target_user_id=None,
                now=now,
                details={**_name_details(old, "old_"), **_name_details(names)},
            )
        await session.flush()
        return category(row)


async def category_usage(session: AsyncSession, category_id: str) -> CategoryUsage:
    """What deleting a category would move, for the confirmation (ADM-01)."""
    async with session.begin():
        row = _find(await reference_repo.categories_in_order(session), category_id)
        return CategoryUsage(
            ingredients=await ingredients_repo.count_in_category(session, row.id),
            extra_items=len(await lists_repo.draft_extras_in_category(session, row.id)),
        )


async def delete_category(
    session: AsyncSession, actor: Principal, category_id: str, *, now: datetime
) -> None:
    """Admins delete a category (REF-01, plan § 6); *Other* and *Uncategorized* always exist
    (409 `category.not_deletable`). In one transaction:

    1. its ingredients move to *Uncategorized*, which isn't an edit of theirs;
    2. its free-text items on drafts that aren't deleted move to *Other*;
    3. nothing on lists being shopped or done lists changes: they keep showing it (D-30);
    4. it is marked deleted, and the others close the gap in the walking order;
    5. `category.delete` records its names and what moved.
    """
    async with session.begin():
        rows = await reference_repo.categories_in_order(session)
        row = _find(rows, category_id)
        if row.key in (OTHER_CATEGORY, UNCATEGORIZED_CATEGORY):
            raise ApiError(ErrorCode.CATEGORY_NOT_DELETABLE, status_code=409)
        built_in = {other.key: other for other in _shown(rows) if other.key is not None}
        moved = await ingredients_repo.move_category(
            session, row.id, built_in[UNCATEGORIZED_CATEGORY].id
        )
        extras = await lists_repo.draft_extras_in_category(session, row.id)
        for extra in extras:
            extra.category_id = built_in[OTHER_CATEGORY].id
            extra.updated_at = now
        await lists_repo.bump(session, {extra.list_id for extra in extras}, now)
        row.deleted_at = row.updated_at = now
        for position, other in enumerate(_shown(rows)):
            if other.sort_order != position:
                other.sort_order = position
                other.updated_at = now
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.CATEGORY_DELETE,
            target_user_id=None,
            now=now,
            details={
                **_name_details(category(row).names),
                "ingredients": moved,
                "extra_items": len(extras),
            },
        )
        await session.flush()
