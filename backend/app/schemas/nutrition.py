"""Nutrient schemas, generated from the registry `app.domain.nutrients.NUTRIENTS` (MNT-06).

Each nutrient of the registry becomes one field named by its key. Type checkers see the classes
declared under `TYPE_CHECKING` without fields, so code reads and writes them by key
(`model_dump()`, `model_validate()`, `model_fields_set`).
"""

from typing import TYPE_CHECKING, Annotated, Any, Literal

from pydantic import BaseModel, Field, create_model

from app.domain.nutrients import NUTRIENTS

NutrientSource = Literal["manual", "products", "unknown"]


class NutrientInfo(BaseModel):
    """An ingredient's value for one nutrient, decided field by field (NUT-02): the manual
    value, else the average over its products that have one, else unknown (null, never 0).
    `products_mean` is that average (shown as a hint next to a manual value)."""

    value: float | None
    source: NutrientSource
    products_mean: float | None
    products_count: int


def _nutrient_values() -> type[BaseModel]:
    fields: dict[str, Any] = {
        nutrient.key: (
            Annotated[float, Field(ge=0, le=nutrient.max_per_100, allow_inf_nan=False)] | None,
            None,
        )
        for nutrient in NUTRIENTS
    }
    return create_model(
        "NutrientValues",
        __doc__="Values per 100 g or 100 ml; null means unknown. In requests every value must "
        "be plausible: 0 up to the nutrient's maximum (900 kcal, 100 g for the others).",
        __module__=__name__,
        **fields,
    )


def _ingredient_nutrition() -> type[BaseModel]:
    fields: dict[str, Any] = {nutrient.key: (NutrientInfo, ...) for nutrient in NUTRIENTS}
    return create_model(
        "IngredientNutrition",
        __doc__="The ingredient's value per nutrient (NUT-02).",
        __module__=__name__,
        **fields,
    )


if TYPE_CHECKING:

    class NutrientValues(BaseModel):
        """One optional float field per nutrient key."""

    class IngredientNutrition(BaseModel):
        """One `NutrientInfo` field per nutrient key."""

else:
    NutrientValues = _nutrient_values()
    IngredientNutrition = _ingredient_nutrition()
