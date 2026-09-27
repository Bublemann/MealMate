"""The nutrients registry and what is generated from it (NUT-01, MNT-06)."""

import math

import pytest

from app.domain.nutrients import NUTRIENT_KEYS, NUTRIENTS, NUTRIENTS_BY_KEY, plausible
from app.models import Ingredient, Product
from app.schemas.nutrition import IngredientNutrition, NutrientValues


def test_registry() -> None:
    assert NUTRIENT_KEYS == ("kcal", "protein", "carbs", "sugar", "fat")
    assert [(n.off_field, n.max_per_100, n.display_unit) for n in NUTRIENTS] == [
        ("energy-kcal_100g", 900, "kcal"),
        ("proteins_100g", 100, "g"),
        ("carbohydrates_100g", 100, "g"),
        ("sugars_100g", 100, "g"),
        ("fat_100g", 100, "g"),
    ]
    assert list(NUTRIENTS_BY_KEY) == list(NUTRIENT_KEYS)


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("kcal", 0, True),
        ("kcal", 900, True),
        ("kcal", 900.01, False),
        ("kcal", -0.01, False),
        ("protein", 100, True),
        ("protein", 100.5, False),
        ("fat", 55.5, True),
        ("sugar", math.nan, False),
        ("carbs", math.inf, False),
        ("carbs", -math.inf, False),
    ],
)
def test_plausible(key: str, value: float, expected: bool) -> None:
    assert plausible(key, value) is expected


def test_columns_and_schemas_come_from_the_registry() -> None:
    for model in (Ingredient, Product):
        columns = model.__table__.columns
        assert all(columns[key].nullable for key in NUTRIENT_KEYS), model
    assert list(NutrientValues.model_fields) == list(NUTRIENT_KEYS)
    assert list(IngredientNutrition.model_fields) == list(NUTRIENT_KEYS)
    for nutrient in NUTRIENTS:
        schema = NutrientValues.model_json_schema()["properties"][nutrient.key]
        assert schema["anyOf"][0]["maximum"] == nutrient.max_per_100


def test_nutrient_accessors() -> None:
    ingredient = Ingredient()
    ingredient.set_nutrients({"kcal": 52.0, "fat": None})
    assert ingredient.nutrients()["kcal"] == 52.0
    assert ingredient.nutrients()["fat"] is None
    with pytest.raises(KeyError):
        ingredient.set_nutrient("salt", 1.0)
