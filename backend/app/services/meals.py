"""Meals: CRUD with ingredient rows, cuisine and tags; copy; photo; nutrition; the "recently
used" meals of the list builder (MEAL-01..10, VIS-01/02/04/05, NUT-03..05, CPL-06).

Who may see or change a meal is decided by `services.access` (`require_meal_view`,
`require_meal_owner`); signed photo URLs are only put into responses after that check (VIS-05).
Nutrition is computed on every read from the live ingredient attributes and values (NUT-06).
Related rows are loaded in batches, so a list or detail takes a fixed number of queries.

Photo files are written before the transaction that refers to them, and old files are deleted
after the transaction that dropped the reference has committed; anything left over is removed by
`mealmate jobs cleanup`. Image processing runs in a worker thread, one image at a time.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldErrorCode, FieldProblem, validation_error
from app.domain.lists import RECENT_MEALS_LIMIT
from app.domain.nutrition import MealRow as NutritionRow
from app.domain.nutrition import meal_nutrition
from app.domain.text import normalize
from app.domain.units import BaseUnit, IngredientAttrs, Unit
from app.media.store import MediaStore
from app.models import Ingredient as IngredientRow
from app.models import Meal as MealRow
from app.models import MealIngredient
from app.models import Tag as TagRow
from app.repositories import ingredients as ingredients_repo
from app.repositories import lists as lists_repo
from app.repositories import meals as meals_repo
from app.repositories import reference as reference_repo
from app.repositories import users as users_repo
from app.schemas.meals import (
    Meal,
    MealBasedOn,
    MealCreate,
    MealIngredientInput,
    MealIngredientRow,
    MealNutrition,
    MealNutritionMissing,
    MealPhoto,
    MealSummary,
    MealUpdate,
)
from app.schemas.nutrition import NutrientValues
from app.schemas.reference import Tag
from app.services import access, hooks
from app.services.ingredients import summary as ingredient_summary
from app.services.principal import Principal
from app.services.reference import cuisine
from app.services.users import user_refs


def _nutrient_values(values: dict[str, float | None]) -> NutrientValues:
    # Totals are not bounded by the per-100 maximums that requests are checked against.
    return NutrientValues.model_construct(None, **values)


def _tag(row: TagRow) -> Tag:
    return Tag(id=row.id, name=row.name)


async def _nutrition_and_rows(
    session: AsyncSession, meal: MealRow
) -> tuple[MealNutrition, list[MealIngredientRow]]:
    rows = (await meals_repo.rows_for(session, [meal.id]))[meal.id]
    ingredient_ids = {row.ingredient_id for row in rows}
    ingredients = await ingredients_repo.by_ids(session, ingredient_ids)

    def attrs(ingredient: IngredientRow) -> IngredientAttrs:
        return IngredientAttrs(
            base_unit=BaseUnit(ingredient.base_unit),
            piece_weight_g=ingredient.piece_weight_g,
            density_g_per_ml=ingredient.density_g_per_ml,
        )

    nutrition = meal_nutrition(
        [
            NutritionRow(
                ingredient_id=row.ingredient_id,
                ingredient_name=ingredients[row.ingredient_id].name,
                amount=row.amount,
                unit=None if row.unit is None else Unit(row.unit),
                attrs=attrs(ingredients[row.ingredient_id]),
                values=ingredients[row.ingredient_id].nutrients(),
            )
            for row in rows
        ],
        meal.servings,
    )
    return (
        MealNutrition(
            per_meal=_nutrient_values(nutrition.totals),
            per_serving=_nutrient_values(nutrition.per_serving),
            incomplete=not nutrition.complete,
            estimate=nutrition.estimate,
            missing=[
                MealNutritionMissing(
                    ingredient_id=item.ingredient_id,
                    ingredient_name=item.ingredient_name,
                    ingredient_brand=ingredients[item.ingredient_id].brand,
                    reason=item.reason,
                    nutrient=item.nutrient,
                )
                for item in nutrition.missing
            ],
        ),
        [
            MealIngredientRow(
                id=row.id,
                position=row.position,
                ingredient=ingredient_summary(ingredients[row.ingredient_id]),
                amount=row.amount,
                unit=None if row.unit is None else Unit(row.unit),
                note=row.note,
            )
            for row in rows
        ],
    )


async def _meal(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    meal: MealRow,
    *,
    now: datetime,
) -> Meal:
    """The detail view of a meal the principal may see."""
    nutrition, rows = await _nutrition_and_rows(session, meal)
    tags = (await meals_repo.tags_for(session, [meal.id]))[meal.id]
    cuisine_row = (
        None
        if meal.cuisine_id is None
        else await reference_repo.get_cuisine(session, meal.cuisine_id)
    )
    original = (
        None
        if meal.copied_from_meal_id is None
        else await meals_repo.get(session, meal.copied_from_meal_id)
    )
    if original is not None and not await access.may_view_meals_of(
        session, principal.user_id, original.owner_id
    ):
        original = None  # "based on" disappears when the original becomes invisible (MEAL-08)
    refs = await user_refs(
        session, [meal.owner_id, None if original is None else original.owner_id]
    )
    photo = None if meal.photo_key is None else media.signed(meal.photo_key, now=now)
    return Meal(
        id=meal.id,
        name=meal.name,
        owner=refs[meal.owner_id],
        is_owner=meal.owner_id == principal.user_id,
        instructions=meal.instructions,
        source_url=meal.source_url,
        servings=meal.servings,
        cuisine=None if cuisine_row is None else cuisine(cuisine_row),
        tags=[_tag(tag) for tag in tags],
        photo=None if photo is None else MealPhoto(url=photo.url, thumb_url=photo.thumb_url),
        ingredients=rows,
        nutrition=nutrition,
        based_on=(
            None
            if original is None
            else MealBasedOn(meal_id=original.id, name=original.name, owner=refs[original.owner_id])
        ),
        created_at=meal.created_at,
        updated_at=meal.updated_at,
    )


def _row_problems(rows: Sequence[MealIngredientInput]) -> list[FieldProblem]:
    """A unit needs an amount."""
    return [
        FieldProblem(("body", "ingredients", index, "amount"), FieldErrorCode.REQUIRED)
        for index, row in enumerate(rows)
        if row.unit is not None and row.amount is None
    ]


async def _check_references(
    session: AsyncSession,
    *,
    cuisine_id: str | None,
    rows: Sequence[MealIngredientInput] | None,
    problems: list[FieldProblem],
) -> None:
    """Refuse (422) unknown cuisines and ingredients, together with the other `problems`."""
    found: list[FieldProblem] = []
    if cuisine_id is not None and await reference_repo.get_cuisine(session, cuisine_id) is None:
        found.append(FieldProblem(("body", "cuisine_id"), FieldErrorCode.INVALID))
    if rows:
        known = await ingredients_repo.by_ids(session, (row.ingredient_id for row in rows))
        found.extend(
            FieldProblem(("body", "ingredients", index, "ingredient_id"), FieldErrorCode.INVALID)
            for index, row in enumerate(rows)
            if row.ingredient_id not in known
        )
    if found or problems:
        raise validation_error([*found, *problems])


async def _set_tags(
    session: AsyncSession, meal_id: str, names: Iterable[str], *, now: datetime
) -> None:
    """Replace the meal's tags: existing tags are reused by normalised name, missing ones are
    created with the spelling given first (REF-04)."""
    wanted: dict[str, str] = {}
    for name in names:
        wanted.setdefault(normalize(name), name)
    tags = await reference_repo.tags_by_name_norm(session, wanted)
    for name_norm, name in wanted.items():
        if name_norm not in tags:
            tags[name_norm] = TagRow(name=name, name_norm=name_norm, created_at=now, updated_at=now)
            session.add(tags[name_norm])
    await session.flush()
    await meals_repo.set_tags(session, meal_id, (tags[name_norm].id for name_norm in wanted))


async def _set_rows(
    session: AsyncSession,
    meal_id: str,
    existing: Sequence[MealIngredient],
    rows: Sequence[MealIngredientInput],
    *,
    now: datetime,
) -> None:
    """Replace the meal's rows, reusing the existing ones by position (their ids stay). An
    amount without a unit counts as pieces."""
    for position, item in enumerate(rows):
        unit = Unit.PIECE if item.unit is None and item.amount is not None else item.unit
        values = {
            "ingredient_id": item.ingredient_id,
            "amount": item.amount,
            "unit": None if unit is None else unit.value,
            "note": item.note,
        }
        if position >= len(existing):
            session.add(
                MealIngredient(
                    meal_id=meal_id, position=position, created_at=now, updated_at=now, **values
                )
            )
            continue
        row = existing[position]
        if any(getattr(row, name) != value for name, value in values.items()):
            for name, value in values.items():
                setattr(row, name, value)
            row.updated_at = now
    for row in existing[len(rows) :]:
        await session.delete(row)


async def _summaries(
    session: AsyncSession, media: MediaStore, rows: Sequence[MealRow], *, now: datetime
) -> list[MealSummary]:
    refs = await user_refs(session, {row.owner_id for row in rows})
    cuisines = await reference_repo.cuisines_by_ids(session, (row.cuisine_id for row in rows))
    tags = await meals_repo.tags_for(session, (row.id for row in rows))
    return [
        MealSummary(
            id=row.id,
            name=row.name,
            owner=refs[row.owner_id],
            cuisine=None if row.cuisine_id is None else cuisine(cuisines[row.cuisine_id]),
            tags=[_tag(tag) for tag in tags.get(row.id, [])],
            servings=row.servings,
            thumb_url=None if row.photo_key is None else media.thumb_url(row.photo_key, now=now),
            updated_at=row.updated_at,
        )
        for row in rows
    ]


async def list_meals(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    *,
    query: str | None,
    cuisine_id: str | None,
    tag_id: str | None,
    owner_ids: Sequence[str] | None,
    now: datetime,
) -> list[MealSummary]:
    """The meals the principal may see (VIS-01/02, CPL-04), A-Z (MEAL-09).

    Without `owner_ids`, the owners the principal switched off in their filter chips are left
    out (MEAL-10); with them, only those owners' meals are listed (as far as visible). `query`
    matches the name, a tag or the cuisine, ignoring case, umlauts and accents.
    """
    async with session.begin():
        visible = await access.visible_owner_ids(session, principal.user_id, "meals")
        if owner_ids is not None:
            owners = visible & set(owner_ids)
        else:
            viewer = await users_repo.get(session, principal.user_id)
            hidden = set() if viewer is None else set(viewer.filter_hidden.get("meals", []))
            owners = visible - hidden
        rows = await meals_repo.search(
            session,
            owner_ids=owners,
            query=normalize(query or ""),
            cuisine_id=cuisine_id,
            tag_id=tag_id,
        )
        return await _summaries(session, media, rows, now=now)


async def recent_meals(
    session: AsyncSession, media: MediaStore, principal: Principal, *, now: datetime
) -> list[MealSummary]:
    """The meals the principal added to lists, most recently added first and each once, as
    far as they still exist and are visible to them (MEAL-09: "recently used" in the meal
    picker); at most 10. Filter chips do not apply."""
    async with session.begin():
        visible = await access.visible_owner_ids(session, principal.user_id, "meals")
        meal_ids = await lists_repo.recent_meal_ids(
            session, principal.user_id, visible, RECENT_MEALS_LIMIT
        )
        meals = await meals_repo.by_ids(session, meal_ids)
        return await _summaries(session, media, [meals[meal_id] for meal_id in meal_ids], now=now)


async def list_meal_tags(session: AsyncSession, principal: Principal) -> list[Tag]:
    """The tags on the meals the principal may see (VIS-01/02, CPL-04), by name: the choices of
    the Meals tab's tag filter (MEAL-09). Filter chips (MEAL-10) do not narrow them, and tags
    only used on meals the principal cannot see are left out."""
    async with session.begin():
        visible = await access.visible_owner_ids(session, principal.user_id, "meals")
        tags = await meals_repo.tags_of_owners(session, visible)
    return [_tag(tag) for tag in tags]


async def get_meal(
    session: AsyncSession, media: MediaStore, principal: Principal, meal_id: str, *, now: datetime
) -> Meal:
    """A meal the principal may see (404 otherwise), with its nutrition (MEAL-06)."""
    async with session.begin():
        meal = await access.require_meal_view(session, principal, meal_id)
        return await _meal(session, media, principal, meal, now=now)


async def create_meal(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    body: MealCreate,
    *,
    now: datetime,
) -> Meal:
    """Add a meal owned by the principal (MEAL-01, MEAL-02)."""
    problems = _row_problems(body.ingredients)
    async with session.begin():
        await _check_references(
            session, cuisine_id=body.cuisine_id, rows=body.ingredients, problems=problems
        )
        meal = MealRow(
            owner_id=principal.user_id,
            name=body.name,
            name_norm=normalize(body.name),
            instructions=body.instructions,
            source_url=body.source_url,
            servings=body.servings,
            cuisine_id=body.cuisine_id,
            created_at=now,
            updated_at=now,
        )
        session.add(meal)
        await session.flush()
        await _set_tags(session, meal.id, body.tags, now=now)
        await _set_rows(session, meal.id, [], body.ingredients, now=now)
        await session.flush()
        return await _meal(session, media, principal, meal, now=now)


async def update_meal(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    meal_id: str,
    body: MealUpdate,
    *,
    now: datetime,
) -> Meal:
    """Change the fields that were sent (owner only, MEAL-07); `tags` and `ingredients`
    replace the whole list."""
    sent = body.model_fields_set
    problems = _row_problems(body.ingredients or [])
    async with session.begin():
        meal = await access.require_meal_owner(session, principal, meal_id)
        await _check_references(
            session, cuisine_id=body.cuisine_id, rows=body.ingredients, problems=problems
        )
        if body.name is not None:
            meal.name, meal.name_norm = body.name, normalize(body.name)
        if "instructions" in sent:
            meal.instructions = body.instructions
        if "source_url" in sent:
            meal.source_url = body.source_url
        if body.servings is not None:
            meal.servings = body.servings
        if "cuisine_id" in sent:
            meal.cuisine_id = body.cuisine_id
        if body.tags is not None:
            await _set_tags(session, meal.id, body.tags, now=now)
        if body.ingredients is not None:
            existing = (await meals_repo.rows_for(session, [meal.id]))[meal.id]
            await _set_rows(session, meal.id, existing, body.ingredients, now=now)
        meal.updated_at = now
        await session.flush()
        return await _meal(session, media, principal, meal, now=now)


async def delete_meal(
    session: AsyncSession, media: MediaStore, principal: Principal, meal_id: str, *, now: datetime
) -> None:
    """Delete a meal (owner only, MEAL-07); it is detached from the lists it is on (LIST-15)
    and its photo files go after the commit."""
    async with session.begin():
        meal = await access.require_meal_owner(session, principal, meal_id)
        photo_key = meal.photo_key
        await hooks.on_meal_deleted(session, meal.id, now=now)
        await session.delete(meal)
    if photo_key is not None:
        await media.delete_in_thread(photo_key)


async def copy_meal(
    session: AsyncSession, media: MediaStore, principal: Principal, meal_id: str, *, now: datetime
) -> Meal:
    """Copy a visible meal to the principal's meals (MEAL-08): same name, instructions, source
    link, servings, cuisine, tags and rows, its own copy of the photo files, and a reference to
    the original ("based on"). Copying one's own meal is allowed."""
    async with session.begin():
        original = await access.require_meal_view(session, principal, meal_id)
        photo_key = original.photo_key
    # The files are copied outside the transaction; if it fails, the cleanup job removes them.
    new_photo_key = None if photo_key is None else await media.copy_in_thread(photo_key)
    session.expire_all()
    async with session.begin():
        original = await access.require_meal_view(session, principal, meal_id)
        meal = MealRow(
            owner_id=principal.user_id,
            name=original.name,
            name_norm=original.name_norm,
            instructions=original.instructions,
            source_url=original.source_url,
            servings=original.servings,
            cuisine_id=original.cuisine_id,
            photo_key=new_photo_key,
            copied_from_meal_id=original.id,
            created_at=now,
            updated_at=now,
        )
        session.add(meal)
        await session.flush()
        tags = (await meals_repo.tags_for(session, [original.id]))[original.id]
        await meals_repo.set_tags(session, meal.id, (tag.id for tag in tags))
        session.add_all(
            MealIngredient(
                meal_id=meal.id,
                position=row.position,
                ingredient_id=row.ingredient_id,
                amount=row.amount,
                unit=row.unit,
                note=row.note,
                created_at=now,
                updated_at=now,
            )
            for row in (await meals_repo.rows_for(session, [original.id]))[original.id]
        )
        await session.flush()
        return await _meal(session, media, principal, meal, now=now)


async def set_photo(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    meal_id: str,
    data: bytes,
    *,
    now: datetime,
) -> Meal:
    """Replace the meal's photo (owner only, MEAL-04): the upload is checked, rotated upright
    and re-encoded in a worker thread (413/415/422 `media.*` if it is refused), stored under a
    new random key, and the previous files are deleted after the commit."""
    async with session.begin():
        await access.require_meal_owner(session, principal, meal_id)
    photo_key = await media.process_and_write(data)
    session.expire_all()
    async with session.begin():
        meal = await access.require_meal_owner(session, principal, meal_id)
        previous_key, meal.photo_key = meal.photo_key, photo_key
        meal.updated_at = now
        await session.flush()
        result = await _meal(session, media, principal, meal, now=now)
    if previous_key is not None:
        await media.delete_in_thread(previous_key)
    return result


async def delete_photo(
    session: AsyncSession, media: MediaStore, principal: Principal, meal_id: str, *, now: datetime
) -> None:
    """Remove the meal's photo (owner only); nothing happens if it has none."""
    async with session.begin():
        meal = await access.require_meal_owner(session, principal, meal_id)
        photo_key = meal.photo_key
        if photo_key is not None:
            meal.photo_key = None
            meal.updated_at = now
    if photo_key is not None:
        await media.delete_in_thread(photo_key)
