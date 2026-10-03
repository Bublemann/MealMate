"""Queries on `meals`, `meal_ingredients` and `meal_tags`.

Lists and details load related rows in batches (rows, tags per meal id), so the number of
queries does not grow with the number of meals (PERF).
"""

from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cuisine, Meal, MealIngredient, MealTag, Tag
from app.repositories.search import contains


async def get(session: AsyncSession, meal_id: str) -> Meal | None:
    return await session.get(Meal, meal_id)


async def by_ids(session: AsyncSession, meal_ids: Iterable[str | None]) -> dict[str, Meal]:
    ids = {meal_id for meal_id in meal_ids if meal_id is not None}
    if not ids:
        return {}
    result = await session.execute(select(Meal).where(Meal.id.in_(ids)))
    return {row.id: row for row in result.scalars()}


async def search(
    session: AsyncSession,
    *,
    owner_ids: Collection[str],
    query: str,
    cuisine_ids: Collection[str],
    tag_ids: Collection[str],
) -> Sequence[Meal]:
    """Meals of the given owners in dictionary order (then by id). A normalised `query`
    matches the meal name, a tag name or the cuisine (its key or name), also with umlaut
    spellings folded. With `cuisine_ids`, only meals in any of those cuisines; with `tag_ids`,
    only meals that have every one of those tags."""
    if not owner_ids:
        return []
    statement = select(Meal).where(Meal.owner_id.in_(owner_ids))
    if cuisine_ids:
        statement = statement.where(Meal.cuisine_id.in_(cuisine_ids))
    for tag_id in dict.fromkeys(tag_ids):
        statement = statement.where(
            exists().where(MealTag.meal_id == Meal.id, MealTag.tag_id == tag_id)
        )
    if query:
        name_matches, _ = contains(Meal.name_norm, query)
        tag_matches, _ = contains(Tag.name_norm, query)
        # A seeded cuisine's `name_norm` is its key, a user-added one's its normalised name.
        cuisine_matches, _ = contains(Cuisine.name_norm, query)
        statement = statement.where(
            or_(
                name_matches,
                exists()
                .where(MealTag.meal_id == Meal.id, MealTag.tag_id == Tag.id)
                .where(tag_matches),
                exists().where(Cuisine.id == Meal.cuisine_id).where(cuisine_matches),
            )
        )
    result = await session.execute(statement.order_by(Meal.name_sort, Meal.id))
    return result.scalars().all()


async def rows_for(
    session: AsyncSession, meal_ids: Iterable[str]
) -> dict[str, list[MealIngredient]]:
    """The ingredient rows per meal id, by position."""
    ids = set(meal_ids)
    rows: dict[str, list[MealIngredient]] = defaultdict(list)
    if ids:
        result = await session.execute(
            select(MealIngredient)
            .where(MealIngredient.meal_id.in_(ids))
            .order_by(MealIngredient.meal_id, MealIngredient.position)
        )
        for row in result.scalars():
            rows[row.meal_id].append(row)
    return rows


async def tags_for(session: AsyncSession, meal_ids: Iterable[str]) -> dict[str, list[Tag]]:
    """The tags per meal id, by normalised name."""
    ids = set(meal_ids)
    tags: dict[str, list[Tag]] = defaultdict(list)
    if ids:
        result = await session.execute(
            select(MealTag.meal_id, Tag)
            .join(Tag, Tag.id == MealTag.tag_id)
            .where(MealTag.meal_id.in_(ids))
            .order_by(Tag.name_norm)
        )
        for meal_id, tag in result:
            tags[meal_id].append(tag)
    return tags


async def tags_of_owners(session: AsyncSession, owner_ids: Collection[str]) -> Sequence[Tag]:
    """The distinct tags on meals of the given owners, by normalised name (then id)."""
    result = await session.execute(
        select(Tag)
        .where(
            exists()
            .where(MealTag.tag_id == Tag.id, MealTag.meal_id == Meal.id)
            .where(Meal.owner_id.in_(owner_ids))
        )
        .order_by(Tag.name_norm, Tag.id)
    )
    return result.scalars().all()


async def set_tags(session: AsyncSession, meal_id: str, tag_ids: Iterable[str]) -> None:
    """Replace the meal's tags."""
    await session.execute(delete(MealTag).where(MealTag.meal_id == meal_id))
    session.add_all(MealTag(meal_id=meal_id, tag_id=tag_id) for tag_id in dict.fromkeys(tag_ids))


async def count_with_ingredient(session: AsyncSession, ingredient_id: str) -> int:
    """How many meals have at least one row of the ingredient."""
    result = await session.execute(
        select(func.count(func.distinct(MealIngredient.meal_id))).where(
            MealIngredient.ingredient_id == ingredient_id
        )
    )
    return result.scalar_one()


async def amounts_of(
    session: AsyncSession, ingredient_id: str
) -> list[tuple[str, float | None, str | None]]:
    """The meal id, amount and unit of every row of the ingredient."""
    result = await session.execute(
        select(MealIngredient.meal_id, MealIngredient.amount, MealIngredient.unit).where(
            MealIngredient.ingredient_id == ingredient_id
        )
    )
    return [(meal_id, amount, unit) for meal_id, amount, unit in result]


async def repoint_ingredient(session: AsyncSession, from_id: str, into_id: str) -> None:
    """Rows of one ingredient now refer to another (merge, ING-05); positions stay."""
    await session.execute(
        update(MealIngredient)
        .where(MealIngredient.ingredient_id == from_id)
        .values(ingredient_id=into_id)
    )


async def photo_keys(session: AsyncSession) -> set[str]:
    """Every photo key a meal refers to."""
    result = await session.execute(select(Meal.photo_key).where(Meal.photo_key.is_not(None)))
    return {key for key in result.scalars() if key is not None}
