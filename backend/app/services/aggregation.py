"""The aggregation service: the lines of a list from its meals and extra items (AGG, LIST-05..08,
LIST-15, plan § 5.6 steps 1-8).

It only turns the list's content into `Part`s and lets `domain.aggregation` group, total, round
and sort them; no amounts are calculated here or in the frontend (AGG-01).

1. A live list meal (`frozen_at` null) contributes the meal's current rows with the live
   ingredient attributes; a frozen or detached one its `list_meal_ingredients` with the
   attributes captured then. Each row is scaled by `servings ÷ meal servings` (LIST-04).
2. A linked extra item contributes to its ingredient's line with the live attributes (in a
   draft; M5b uses `attrs_snapshot` once shopping started). A free-text item is a line of its
   own, `x:<id>`, without amounts: its `amount_text` is shown as it is.
3. An ingredient line shows the live ingredient's name and category, a free-text line its
   text and category. Lines are sorted by category order, then normalised name, then key
   (AGG-05), and carry their hidden state (LIST-07).

Everything is loaded in batches for any number of lists (`load`), so reading a list or the
summaries of many takes a fixed number of queries.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregation import Part, SourceRef, aggregate
from app.domain.lists import INGREDIENT_KEY_PREFIX, TEXT_KEY_PREFIX, ingredient_key, text_key
from app.domain.reference import OTHER_CATEGORY
from app.domain.text import normalize
from app.domain.units import BaseUnit, IngredientAttrs, Unit
from app.models import (
    Category,
    Ingredient,
    ListExtraItem,
    ListLineState,
    ListMeal,
    ListMealIngredient,
    Meal,
    MealIngredient,
    ShoppingList,
)
from app.repositories import ingredients as ingredients_repo
from app.repositories import lists as lists_repo
from app.repositories import meals as meals_repo
from app.repositories import reference as reference_repo
from app.schemas.lists import DisplayAmountOut, LineSource, ListLine


@dataclass(frozen=True)
class ListContent:
    """Everything the lines of some lists are computed from.

    `meals`, `extras` (not deleted) and `states` are per list id; `live_meals` and `meal_rows`
    per meal id (live list meals only); `frozen_rows` per list meal id.
    """

    meals: dict[str, list[ListMeal]]
    live_meals: dict[str, Meal]
    meal_rows: dict[str, list[MealIngredient]]
    frozen_rows: dict[str, list[ListMealIngredient]]
    extras: dict[str, list[ListExtraItem]]
    ingredients: dict[str, Ingredient]
    categories: dict[str, Category]
    states: dict[str, dict[str, ListLineState]]

    def live_meal(self, list_meal: ListMeal) -> Meal | None:
        """The meal a live list meal takes its rows from; None once it is frozen."""
        if list_meal.frozen_at is not None or list_meal.meal_id is None:
            return None
        return self.live_meals.get(list_meal.meal_id)

    def other_category_id(self) -> str:
        return next(row.id for row in self.categories.values() if row.key == OTHER_CATEGORY)


def is_live(list_meal: ListMeal) -> bool:
    return list_meal.frozen_at is None and list_meal.meal_id is not None


async def load(session: AsyncSession, list_ids: Iterable[str]) -> ListContent:
    """The content of the given lists, in eight queries whatever their size."""
    ids = set(list_ids)
    meals = await lists_repo.meals_for(session, ids)
    list_meals = [list_meal for group in meals.values() for list_meal in group]
    live_ids = {list_meal.meal_id for list_meal in list_meals if is_live(list_meal)}
    live_meals = await meals_repo.by_ids(session, live_ids)
    meal_rows = await meals_repo.rows_for(session, live_meals)
    frozen_rows = await lists_repo.frozen_rows_for(
        session, (list_meal.id for list_meal in list_meals if not is_live(list_meal))
    )
    extras = await lists_repo.extras_for(session, ids)
    ingredient_ids = {
        *(row.ingredient_id for rows in meal_rows.values() for row in rows),
        *(row.ingredient_id for rows in frozen_rows.values() for row in rows),
        *(extra.ingredient_id for group in extras.values() for extra in group),
    }
    ingredients = await ingredients_repo.by_ids(
        session, (ingredient_id for ingredient_id in ingredient_ids if ingredient_id is not None)
    )
    categories = {row.id: row for row in await reference_repo.categories_in_order(session)}
    states = await lists_repo.states_for(session, ids)
    return ListContent(
        meals=meals,
        live_meals=live_meals,
        meal_rows=meal_rows,
        frozen_rows=frozen_rows,
        extras=extras,
        ingredients=ingredients,
        categories=categories,
        states=states,
    )


def live_attrs(ingredient: Ingredient) -> IngredientAttrs:
    return IngredientAttrs(
        base_unit=BaseUnit(ingredient.base_unit),
        piece_weight_g=ingredient.piece_weight_g,
        density_g_per_ml=ingredient.density_g_per_ml,
    )


def _snapshot_attrs(row: ListMealIngredient) -> IngredientAttrs:
    return IngredientAttrs(
        base_unit=BaseUnit(row.base_unit_snapshot),
        piece_weight_g=row.piece_weight_g_snapshot,
        density_g_per_ml=row.density_snapshot,
    )


def _part(
    ingredient_id: str,
    amount: float | None,
    unit: str | None,
    attrs: IngredientAttrs,
    source: SourceRef,
    factor: float = 1.0,
) -> Part:
    return Part(
        line_key=ingredient_key(ingredient_id),
        amount=None if amount is None else amount * factor,
        unit=None if unit is None else Unit(unit),
        attrs=attrs,
        source=source,
    )


def _meal_parts(content: ListContent, list_meal: ListMeal) -> list[Part]:
    source = SourceRef("meal", list_meal.id)
    if (meal := content.live_meal(list_meal)) is not None:
        factor = list_meal.servings / meal.servings
        return [
            _part(
                row.ingredient_id,
                row.amount,
                row.unit,
                live_attrs(content.ingredients[row.ingredient_id]),
                source,
                factor,
            )
            for row in content.meal_rows.get(meal.id, [])
        ]
    factor = list_meal.servings / list_meal.meal_servings_snapshot
    return [
        _part(row.ingredient_id, row.amount, row.unit, _snapshot_attrs(row), source, factor)
        for row in content.frozen_rows.get(list_meal.id, [])
    ]


def _extra_part(content: ListContent, extra: ListExtraItem) -> Part:
    source = SourceRef("extra", extra.id)
    if extra.ingredient_id is None:
        return Part(line_key=text_key(extra.id), amount=None, unit=None, attrs=None, source=source)
    attrs = live_attrs(content.ingredients[extra.ingredient_id])
    return _part(extra.ingredient_id, extra.amount, extra.unit, attrs, source)


def parts(content: ListContent, shopping_list: ShoppingList) -> list[Part]:
    """The parts of a list: its meals in the order they were added, then its extra items."""
    meal_parts = [
        part
        for list_meal in content.meals.get(shopping_list.id, [])
        for part in _meal_parts(content, list_meal)
    ]
    extra_parts = [
        _extra_part(content, extra) for extra in content.extras.get(shopping_list.id, [])
    ]
    return meal_parts + extra_parts


def _hidden_keys(content: ListContent, shopping_list: ShoppingList) -> set[str]:
    states = content.states.get(shopping_list.id, {})
    return {key for key, state in states.items() if state.hidden}


def line_count(content: ListContent, shopping_list: ShoppingList) -> int:
    """How many lines the list has that are not hidden."""
    keys = {part.line_key for part in parts(content, shopping_list)}
    return len(keys - _hidden_keys(content, shopping_list))


def meal_name(content: ListContent, list_meal: ListMeal) -> str:
    """The current name of a live meal, else the one it had when it was frozen."""
    meal = content.live_meal(list_meal)
    return list_meal.meal_name_snapshot if meal is None else meal.name


def lines(
    content: ListContent, shopping_list: ShoppingList, *, private_meals: Collection[str]
) -> list[ListLine]:
    """The aggregated lines of a list, sorted (AGG-05). Sources from the list meals in
    `private_meals` (ids) show no meal name (VIS-06)."""
    list_meals = {row.id: row for row in content.meals.get(shopping_list.id, [])}
    extras = {row.id: row for row in content.extras.get(shopping_list.id, [])}
    other_category_id = content.other_category_id()

    def describe(line_key: str) -> tuple[str, str]:
        """The name and category id of a line."""
        if line_key.startswith(INGREDIENT_KEY_PREFIX):
            ingredient = content.ingredients[line_key.removeprefix(INGREDIENT_KEY_PREFIX)]
            return ingredient.name, ingredient.category_id
        extra = extras[line_key.removeprefix(TEXT_KEY_PREFIX)]
        return extra.text or "", extra.category_id or other_category_id

    def order(line_key: str) -> tuple[int, str]:
        name, category_id = describe(line_key)
        return content.categories[category_id].sort_order, normalize(name)

    def source(ref: SourceRef) -> LineSource:
        if ref.kind == "meal":
            list_meal = list_meals[ref.id]
            private = list_meal.id in private_meals
            return LineSource(
                kind="meal",
                list_meal_id=list_meal.id,
                extra_id=None,
                meal_name=None if private else meal_name(content, list_meal),
                private=private,
                servings=list_meal.servings,
                amount=None,
                unit=None,
                amount_text=None,
            )
        extra = extras[ref.id]
        return LineSource(
            kind="extra",
            list_meal_id=None,
            extra_id=extra.id,
            meal_name=None,
            private=False,
            servings=None,
            amount=extra.amount,
            unit=None if extra.unit is None else Unit(extra.unit),
            amount_text=extra.amount_text,
        )

    hidden = _hidden_keys(content, shopping_list)
    result = []
    for line in aggregate(parts(content, shopping_list), order):
        name, category_id = describe(line.line_key)
        is_ingredient = line.line_key.startswith(INGREDIENT_KEY_PREFIX)
        text_extra = None if is_ingredient else extras[line.line_key.removeprefix(TEXT_KEY_PREFIX)]
        result.append(
            ListLine(
                key=line.line_key,
                kind="ingredient" if is_ingredient else "text",
                ingredient_id=(
                    line.line_key.removeprefix(INGREDIENT_KEY_PREFIX) if is_ingredient else None
                ),
                name=name,
                category_id=category_id,
                amounts=[
                    DisplayAmountOut(value=item.value, unit=item.unit) for item in line.display
                ],
                has_unspecified=is_ingredient and line.totals.has_unspecified,
                amount_text=None if text_extra is None else text_extra.amount_text,
                hidden=line.line_key in hidden,
                sources=[source(ref) for ref in line.sources],
            )
        )
    return result
