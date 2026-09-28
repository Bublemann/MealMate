"""The nutrients registry (NUT-01, MNT-06).

Everything nutrient-shaped is generated from `NUTRIENTS`: the nullable columns on `ingredients`
(each ingredient's own values), the API schema `NutrientValues`, the calculations, and the Open
Food Facts mapping.

Adding a nutrient:
1. add it here (key, OFF field, plausible maximum per 100 g/ml, display unit);
2. run `alembic revision --autogenerate` for the new column, and `make openapi`;
3. add the translations `nutrient.<key>` in `de.json` and `en.json`;
4. extend the tests (plausibility and the OFF mapping).
"""

import math
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Nutrient:
    """`off_field` is the Open Food Facts field per 100 g/ml; `max_per_100` bounds plausible
    values (BAR-10); `display_unit` is what the value is shown in."""

    key: str
    off_field: str
    max_per_100: float
    display_unit: str


NUTRIENTS: tuple[Nutrient, ...] = (
    Nutrient("kcal", "energy-kcal_100g", 900.0, "kcal"),
    Nutrient("protein", "proteins_100g", 100.0, "g"),
    Nutrient("carbs", "carbohydrates_100g", 100.0, "g"),
    Nutrient("sugar", "sugars_100g", 100.0, "g"),
    Nutrient("fat", "fat_100g", 100.0, "g"),
)
NUTRIENT_KEYS: tuple[str, ...] = tuple(nutrient.key for nutrient in NUTRIENTS)
NUTRIENTS_BY_KEY = MappingProxyType({nutrient.key: nutrient for nutrient in NUTRIENTS})


def plausible(key: str, value: float) -> bool:
    """A finite value between 0 and the nutrient's maximum per 100 g/ml (inclusive)."""
    return math.isfinite(value) and 0 <= value <= NUTRIENTS_BY_KEY[key].max_per_100
