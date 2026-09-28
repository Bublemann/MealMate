"""Meal nutrition (NUT-03..05); an ingredient's values are its own columns (NUT-02)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.nutrition import MealRow, Missing, meal_nutrition
from app.domain.units import BaseUnit, IngredientAttrs, Unit

G = IngredientAttrs(BaseUnit.G, piece_weight_g=None, density_g_per_ml=None)
EGG = IngredientAttrs(BaseUnit.G, piece_weight_g=60, density_g_per_ml=None)
MILK = IngredientAttrs(BaseUnit.ML, piece_weight_g=None, density_g_per_ml=1.03)
FULL = dict.fromkeys(NUTRIENT_KEYS, 10.0)


def row(
    name: str,
    amount: float | None,
    unit: Unit | None,
    attrs: IngredientAttrs = G,
    values: dict[str, float | None] | None = None,
) -> MealRow:
    return MealRow(name.lower(), name, amount, unit, attrs, FULL if values is None else values)


def test_meal_nutrition() -> None:
    rows = [
        row("Spaghetti", 500, Unit.G, values={"kcal": 350, "protein": 12, "carbs": 70,
                                               "sugar": 3, "fat": 1.5}),
        row("Eier", 2, Unit.PIECE, EGG, values={"kcal": 155, "protein": 13, "carbs": 1,
                                                 "sugar": 1, "fat": 11}),
        row("Milch", 0.25, Unit.L, MILK, values={"kcal": 64, "protein": 3.4, "carbs": 4.8,
                                                  "sugar": None, "fat": 3.5}),
    ]  # fmt: skip

    result = meal_nutrition(rows, servings=2)

    assert result.totals["kcal"] == pytest.approx(1750 + 186 + 160)
    assert result.totals["protein"] == pytest.approx(60 + 15.6 + 8.5)
    assert result.totals["sugar"] == pytest.approx(15 + 1.2)  # partial: milk unknown
    assert result.per_serving["kcal"] == pytest.approx((1750 + 186 + 160) / 2)
    assert result.missing == [Missing("milch", "Milch", "unknown_value", "sugar")]
    assert not result.complete
    assert not result.estimate


def test_what_cannot_be_counted() -> None:
    rows = [
        row("Salz", None, None),
        row("Pfeffer", 1, None),
        row("Knoblauch", 2, Unit.PIECE),
        row("Mehl", 100, Unit.ML),
        row("Zucker", 1, Unit.TBSP, values={"kcal": 400}),
    ]

    result = meal_nutrition(rows, servings=4)

    assert result.missing == [
        Missing("salz", "Salz", "no_amount"),
        Missing("pfeffer", "Pfeffer", "no_amount"),
        Missing("knoblauch", "Knoblauch", "not_convertible"),
        Missing("mehl", "Mehl", "not_convertible"),
        *(Missing("zucker", "Zucker", "unknown_value", key) for key in NUTRIENT_KEYS[1:]),
    ]
    assert result.totals == {"kcal": pytest.approx(60), **dict.fromkeys(NUTRIENT_KEYS[1:])}
    assert result.per_serving == {"kcal": pytest.approx(15), **dict.fromkeys(NUTRIENT_KEYS[1:])}
    assert result.estimate  # 1 tbsp of sugar counted as 15 g (NUT-05)


def test_an_empty_meal() -> None:
    result = meal_nutrition([], servings=1)
    assert result.totals == dict.fromkeys(NUTRIENT_KEYS)
    assert result.missing == []
    assert result.complete


@pytest.mark.parametrize("servings", [0, -1])
def test_servings_must_be_positive(servings: int) -> None:
    with pytest.raises(ValueError, match="servings"):
        meal_nutrition([], servings=servings)


rows_strategy = st.lists(
    st.builds(
        row,
        name=st.sampled_from(["A", "B", "C"]),
        amount=st.none() | st.floats(0, 5000),
        unit=st.none() | st.sampled_from(Unit),
        attrs=st.sampled_from([G, EGG, MILK]),
        values=st.dictionaries(st.sampled_from(NUTRIENT_KEYS), st.none() | st.floats(0, 100)),
    ),
    max_size=8,
)


@given(data=st.data(), rows=rows_strategy, servings=st.integers(1, 12))
def test_meal_nutrition_properties(data: st.DataObject, rows: list[MealRow], servings: int) -> None:
    result = meal_nutrition(rows, servings)
    shuffled = data.draw(st.permutations(rows))
    assert meal_nutrition(shuffled, servings).totals == result.totals
    for key in NUTRIENT_KEYS:
        total = result.totals[key]
        if total is None:
            assert result.per_serving[key] is None
        else:
            assert total >= 0
            assert result.per_serving[key] == pytest.approx(total / servings)
    assert result.complete is (not result.missing)
