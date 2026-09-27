"""Nutrition of ingredients and meals (NUT-02..06, plan § 5.6).

Nothing here is stored: values are computed when requested, so wiki edits of an ingredient show
up everywhere at once (NUT-06). Unknown is never treated as 0.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.units import IngredientAttrs, Unit, convert

NutrientSource = Literal["manual", "products", "unknown"]
MissingReason = Literal["no_amount", "not_convertible", "unknown_value"]


@dataclass(frozen=True)
class NutrientValue:
    """An ingredient's value for one nutrient and where it comes from. `products_mean` is the
    average over the `products_count` linked products that have a value (the hint next to a
    manual value)."""

    value: float | None
    source: NutrientSource
    products_mean: float | None
    products_count: int


def ingredient_nutrition(
    manual: Mapping[str, float | None], products: Sequence[Mapping[str, float | None]]
) -> dict[str, NutrientValue]:
    """Per nutrient (NUT-02): the manual value, else the mean over the products that have the
    field (each product weighted equally), else unknown."""
    result: dict[str, NutrientValue] = {}
    for key in NUTRIENT_KEYS:
        present = [value for product in products if (value := product.get(key)) is not None]
        mean = math.fsum(present) / len(present) if present else None
        manual_value = manual.get(key)
        if manual_value is not None:
            result[key] = NutrientValue(manual_value, "manual", mean, len(present))
        elif mean is not None:
            result[key] = NutrientValue(mean, "products", mean, len(present))
        else:
            result[key] = NutrientValue(None, "unknown", None, 0)
    return result


@dataclass(frozen=True)
class MealRow:
    """One ingredient row of a meal with the ingredient's attributes and values per 100."""

    ingredient_id: str
    ingredient_name: str
    amount: float | None
    unit: Unit | None
    attrs: IngredientAttrs
    values: Mapping[str, float | None]


@dataclass(frozen=True)
class Missing:
    """Why a row does not (fully) count: no amount, an amount that cannot be converted to the
    ingredient's base unit, or an unknown value for `nutrient`."""

    ingredient_id: str
    ingredient_name: str
    reason: MissingReason
    nutrient: str | None = None


@dataclass(frozen=True)
class MealNutrition:
    """Totals per meal and per serving; a nutrient is None only if nothing contributed to it.
    `missing` makes the result "incomplete" (NUT-04); `estimate` marks spoons counted as
    1 g/ml (NUT-05)."""

    totals: dict[str, float | None]
    per_serving: dict[str, float | None]
    missing: list[Missing]
    estimate: bool

    @property
    def complete(self) -> bool:
        return not self.missing


def meal_nutrition(rows: Sequence[MealRow], servings: int) -> MealNutrition:
    """The sum over rows of (amount in base unit) / 100 * value, with what could not be counted
    (NUT-03, NUT-04). Rows keep their order in `missing`."""
    if servings < 1:
        raise ValueError("servings must be at least 1")
    contributions: dict[str, list[float]] = {key: [] for key in NUTRIENT_KEYS}
    missing: list[Missing] = []
    estimate = False
    for row in rows:
        if row.amount is None or row.unit is None:
            missing.append(Missing(row.ingredient_id, row.ingredient_name, "no_amount"))
            continue
        converted = convert(row.amount, row.unit, row.attrs, allow_estimate=True)
        if converted is None:
            missing.append(Missing(row.ingredient_id, row.ingredient_name, "not_convertible"))
            continue
        estimate = estimate or converted.estimate
        for key in NUTRIENT_KEYS:
            value = row.values.get(key)
            if value is None:
                missing.append(
                    Missing(row.ingredient_id, row.ingredient_name, "unknown_value", key)
                )
            else:
                contributions[key].append(converted.value / 100 * value)
    totals = {key: math.fsum(parts) if parts else None for key, parts in contributions.items()}
    per_serving = {
        key: None if total is None else total / servings for key, total in totals.items()
    }
    return MealNutrition(totals, per_serving, missing, estimate)
