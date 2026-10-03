"""Freezing and detaching list meals (LIST-11, LIST-15, plan § 5.7).

Freezing copies a meal's current rows into `list_meal_ingredients`, with the ingredient's name
and brand and the attributes and category needed to calculate them, and refreshes the meal's
name and servings snapshots, so the list keeps showing the same amounts. The attributes are the
live ones (`Ingredient.attrs()`, D-32): rows frozen since then have no density, and a piece
weight only for an ingredient counted in pieces. Detaching also drops the link to the meal
(`meal_id` null) and says why (`deleted` | `unavailable`); the list owner can then remove it.
Both run inside the caller's transaction and bump the affected lists' versions.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lists import DetachedReason
from app.models import ListMeal, ListMealIngredient
from app.repositories import ingredients as ingredients_repo
from app.repositories import lists as lists_repo
from app.repositories import meals as meals_repo


async def freeze(session: AsyncSession, list_meals: Sequence[ListMeal], *, now: datetime) -> None:
    """Freeze the given live list meals (others are left alone), in a fixed number of
    queries."""
    live = [row for row in list_meals if row.frozen_at is None and row.meal_id is not None]
    meals = await meals_repo.by_ids(session, (row.meal_id for row in live))
    rows = await meals_repo.rows_for(session, meals)
    ingredients = await ingredients_repo.by_ids(
        session, (row.ingredient_id for group in rows.values() for row in group)
    )
    for list_meal in live:
        meal = meals[str(list_meal.meal_id)]
        list_meal.meal_name_snapshot = meal.name
        list_meal.meal_servings_snapshot = meal.servings
        list_meal.frozen_at = now
        list_meal.updated_at = now
        for row in rows.get(meal.id, []):
            ingredient = ingredients[row.ingredient_id]
            attrs = ingredient.attrs()
            session.add(
                ListMealIngredient(
                    list_meal_id=list_meal.id,
                    position=row.position,
                    ingredient_id=row.ingredient_id,
                    ingredient_name_snapshot=ingredient.name,
                    ingredient_brand_snapshot=ingredient.brand,
                    base_unit_snapshot=attrs.base_unit.value,
                    piece_weight_g_snapshot=attrs.piece_weight_g,
                    density_snapshot=attrs.density_g_per_ml,
                    category_id_snapshot=ingredient.category_id,
                    amount=row.amount,
                    unit=row.unit,
                    note=row.note,
                    created_at=now,
                    updated_at=now,
                )
            )
    await lists_repo.bump(session, (row.list_id for row in live), now)


async def detach(
    session: AsyncSession,
    list_meals: Sequence[ListMeal],
    reason: DetachedReason,
    *,
    now: datetime,
) -> None:
    """Detach the given list meals that are not frozen yet (LIST-15); frozen ones are
    unaffected."""
    live = [row for row in list_meals if row.frozen_at is None and row.meal_id is not None]
    await freeze(session, live, now=now)
    for list_meal in live:
        list_meal.meal_id = None
        list_meal.detached_reason = reason
    await session.flush()
