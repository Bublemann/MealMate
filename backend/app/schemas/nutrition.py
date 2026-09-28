"""Nutrient schemas, generated from the registry `app.domain.nutrients.NUTRIENTS` (MNT-06).

Each nutrient of the registry becomes one field named by its key. Type checkers see the classes
declared under `TYPE_CHECKING` without fields, so code reads and writes them by key
(`model_dump()`, `model_validate()`, `model_fields_set`).
"""

from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, Field, create_model

from app.domain.nutrients import NUTRIENTS


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


if TYPE_CHECKING:

    class NutrientValues(BaseModel):
        """One optional float field per nutrient key."""

else:
    NutrientValues = _nutrient_values()
