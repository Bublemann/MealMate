"""Nutrition of meals (NUT-03..06, plan § 5.6).

An ingredient's value per nutrient is its own column (NUT-02, null is unknown), per 100 g, or
per 100 ml for an ml ingredient. A `piece` ingredient's pieces count with its piece weight, and
spoons of a g ingredient as 1 g/ml (NUT-05); an amount that doesn't fit the ingredient's base
unit counts as unknown, never converted (REF-02, D-33). Meal totals are not stored: they are
computed when requested, so wiki edits of an ingredient show up everywhere at once (NUT-06).
Unknown is never treated as 0.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.units import BaseUnit, IngredientAttrs, Unit, convert, counted_unit, fits

MissingReason = Literal["no_amount", "unit_mismatch", "no_piece_weight", "unknown_value"]


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
    """Why a row does not (fully) count: no amount, an amount whose unit doesn't fit the
    ingredient's base unit (REF-02), pieces of a `piece` ingredient without a piece weight, or
    an unknown value for `nutrient`."""

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
    """The sum over rows of (amount in g or ml) / 100 * value, with what could not be counted
    (NUT-03, NUT-04). An amount without a unit counts as pieces. A `piece` ingredient's pieces
    weigh their number times the piece weight (NUT-05). Rows keep their order in `missing`."""
    if servings < 1:
        raise ValueError("servings must be at least 1")
    contributions: dict[str, list[float]] = {key: [] for key in NUTRIENT_KEYS}
    missing: list[Missing] = []
    estimate = False
    for row in rows:
        if row.amount is None:
            missing.append(Missing(row.ingredient_id, row.ingredient_name, "no_amount"))
            continue
        unit = counted_unit(row.amount, row.unit)
        # A fitting amount always converts (with the 1 g/ml estimate), one that doesn't fit
        # never does, whatever piece weight or density the attributes have.
        converted = (
            convert(row.amount, unit, row.attrs, allow_estimate=True)
            if fits(row.amount, unit, row.attrs.base_unit)
            else None
        )
        if converted is None:
            missing.append(Missing(row.ingredient_id, row.ingredient_name, "unit_mismatch"))
            continue
        quantity = converted.value
        if row.attrs.base_unit == BaseUnit.PIECE:
            if not row.attrs.piece_weight_g:
                missing.append(Missing(row.ingredient_id, row.ingredient_name, "no_piece_weight"))
                continue
            quantity *= row.attrs.piece_weight_g
        estimate = estimate or converted.estimate
        for key in NUTRIENT_KEYS:
            value = row.values.get(key)
            if value is None:
                missing.append(
                    Missing(row.ingredient_id, row.ingredient_name, "unknown_value", key)
                )
            else:
                contributions[key].append(quantity / 100 * value)
    totals = {key: math.fsum(parts) if parts else None for key, parts in contributions.items()}
    per_serving = {
        key: None if total is None else total / servings for key, total in totals.items()
    }
    return MealNutrition(totals, per_serving, missing, estimate)
