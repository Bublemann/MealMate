"""Ingredients (ING-01..06, NUT-02)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError

from app.domain.catalog import (
    DENSITY_MAX_G_PER_ML,
    DENSITY_MIN_G_PER_ML,
    INGREDIENT_NAME_MAX_LENGTH,
    PIECE_WEIGHT_MAX_G,
    check_name,
)
from app.schemas.nutrition import IngredientNutrition, NutrientValues
from app.schemas.users import UserRef

# Plain aliases (not `type` statements) so the OpenAPI schema inlines them.
BaseUnitName = Literal["g", "ml"]
IdInput = Annotated[str, StringConstraints(min_length=1, max_length=36)]
IngredientNameInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=INGREDIENT_NAME_MAX_LENGTH),
    AfterValidator(check_name),
]
PieceWeightInput = Annotated[float, Field(gt=0, le=PIECE_WEIGHT_MAX_G, allow_inf_nan=False)]
DensityInput = Annotated[
    float, Field(ge=DENSITY_MIN_G_PER_ML, le=DENSITY_MAX_G_PER_ML, allow_inf_nan=False)
]


def not_null[T](value: T | None) -> T:
    """For update fields that cannot be empty: leaving one out keeps it, an explicit null is
    refused (field code `invalid`) instead of being ignored."""
    if value is None:
        raise PydanticCustomError("not_null", "may not be null")
    return value


class IngredientSummary(BaseModel):
    """A search result or list entry."""

    id: str
    name: str
    category_id: str
    base_unit: BaseUnitName
    product_count: int


class Ingredient(BaseModel):
    """An ingredient with its manual values and the resulting nutrition (NUT-02).

    `created_by` / `updated_by` are null for a deleted user (ING-06).
    """

    id: str
    name: str
    category_id: str
    base_unit: BaseUnitName
    piece_weight_g: float | None
    density_g_per_ml: float | None
    manual: NutrientValues
    nutrition: IngredientNutrition
    product_count: int
    created_by: UserRef | None
    updated_by: UserRef | None
    created_at: datetime
    updated_at: datetime


class IngredientCreate(BaseModel):
    """`category_id` defaults to the *Other* category, `base_unit` to g (ING-02).

    `piece_weight_g`: 0 < x ≤ 10000; `density_g_per_ml`: 0.1 ≤ x ≤ 5.
    """

    name: IngredientNameInput
    category_id: IdInput | None = None
    base_unit: BaseUnitName = "g"
    piece_weight_g: PieceWeightInput | None = None
    density_g_per_ml: DensityInput | None = None
    manual: NutrientValues | None = None


class IngredientUpdate(BaseModel):
    """Only the fields that are sent change; an explicit null clears the piece weight or
    density, and is refused for the name, category and base unit (422 `invalid`). `manual`
    changes only the nutrients it contains (null clears one).

    The base unit cannot change while products are linked (409 `ingredient.base_unit_locked`).
    """

    name: IngredientNameInput | None = None
    category_id: IdInput | None = None
    base_unit: BaseUnitName | None = None
    piece_weight_g: PieceWeightInput | None = None
    density_g_per_ml: DensityInput | None = None
    manual: NutrientValues | None = None

    check_not_null = field_validator("name", "category_id", "base_unit")(not_null)


class IngredientMerge(BaseModel):
    """Merge the ingredient into `into_id` (ING-05)."""

    into_id: IdInput
