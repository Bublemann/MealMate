"""Reference data: categories and their order, units, cuisines, tags (REF-01..04, ADM-01)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldErrorCode, FieldProblem, validation_error
from app.domain.reference import CUISINE_KEYS
from app.domain.text import normalize
from app.domain.units import UNIT_KIND, Unit
from app.models import Category as CategoryRow
from app.models import Cuisine as CuisineRow
from app.repositories import reference as reference_repo
from app.schemas.admin import AdminAction
from app.schemas.reference import Category, CategoryNames, Cuisine, Tag, UnitInfo
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
    )


def cuisine(row: CuisineRow) -> Cuisine:
    return Cuisine(id=row.id, key=row.key, name=row.name)


def _cuisine_order(row: CuisineRow) -> tuple[int, int, str]:
    """Seeded cuisines in seed order (unknown future keys after them), then the rest by name."""
    if row.key is not None:
        return (0, _CUISINE_POSITION.get(row.key, len(CUISINE_KEYS)), row.key)
    return (1, 0, row.name_norm)


async def list_categories(session: AsyncSession) -> list[Category]:
    async with session.begin():
        return [category(row) for row in await reference_repo.categories_in_order(session)]


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
    exactly once; `sort_order` becomes 0..n-1 in that order."""
    async with session.begin():
        rows = await reference_repo.categories_in_order(session)
        by_id = {row.id: row for row in rows}
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
        return [category(by_id[category_id]) for category_id in category_ids]
