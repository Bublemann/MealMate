"""Products: barcodes linked to an ingredient (ING-04, BAR-04)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator

from app.domain.catalog import (
    BARCODE_INPUT_MAX_LENGTH,
    PACK_QUANTITY_MAX,
    PRODUCT_BRAND_MAX_LENGTH,
    PRODUCT_NAME_MAX_LENGTH,
    PRODUCT_QUANTITY_TEXT_MAX_LENGTH,
    check_text,
)
from app.domain.units import Unit
from app.schemas.ingredients import BaseUnitName, IdInput, not_null
from app.schemas.nutrition import NutrientValues
from app.schemas.users import UserRef

ProductSource = Literal["off", "manual"]


def blank_to_none(text: str) -> str | None:
    """Optional texts left empty (after trimming) are stored as null."""
    return text or None


BarcodeInput = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=BARCODE_INPUT_MAX_LENGTH)
]
ProductNameInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=PRODUCT_NAME_MAX_LENGTH),
    AfterValidator(check_text),
    AfterValidator(blank_to_none),
]
BrandInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=PRODUCT_BRAND_MAX_LENGTH),
    AfterValidator(check_text),
    AfterValidator(blank_to_none),
]
QuantityTextInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=PRODUCT_QUANTITY_TEXT_MAX_LENGTH),
    AfterValidator(check_text),
    AfterValidator(blank_to_none),
]
PackQuantityInput = Annotated[float, Field(gt=0, le=PACK_QUANTITY_MAX, allow_inf_nan=False)]


class Product(BaseModel):
    """`nutrients` are per 100 g or 100 ml (`nutrition_basis`, always the ingredient's base
    unit). `user_edited_fields` names the fields a user typed or changed (`name`,
    `nutrients.kcal`, ...); Open Food Facts never overwrites them (BAR-04)."""

    id: str
    barcode: str
    ingredient_id: str
    nutrition_basis: BaseUnitName
    name: str | None
    brand: str | None
    quantity_text: str | None
    pack_quantity: float | None
    pack_unit: Unit | None
    nutrients: NutrientValues
    source: ProductSource
    user_edited_fields: list[str]
    fetched_at: datetime | None
    created_by: UserRef | None
    updated_by: UserRef | None
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    """A product entered by hand. The barcode is EAN-13, EAN-8, UPC-A or UPC-E with a valid
    check digit (spaces are ignored); it is stored as EAN-13 (UPC-A with a leading 0, UPC-E
    expanded first), an EAN-8 as it is. `nutrition_basis` defaults to the ingredient's base unit
    and must match it (409 `product.basis_mismatch`)."""

    barcode: BarcodeInput
    ingredient_id: IdInput
    nutrition_basis: BaseUnitName | None = None
    name: ProductNameInput | None = None
    brand: BrandInput | None = None
    quantity_text: QuantityTextInput | None = None
    pack_quantity: PackQuantityInput | None = None
    pack_unit: Unit | None = None
    nutrients: NutrientValues | None = None


class ProductUpdate(BaseModel):
    """Only the fields that are sent change (null clears an optional one; it is refused for
    the barcode, ingredient and basis with 422 `invalid`); each becomes user-edited.
    `ingredient_id` moves the product to another ingredient, whose base unit must match the
    nutrition basis."""

    barcode: BarcodeInput | None = None
    ingredient_id: IdInput | None = None
    nutrition_basis: BaseUnitName | None = None
    name: ProductNameInput | None = None
    brand: BrandInput | None = None
    quantity_text: QuantityTextInput | None = None
    pack_quantity: PackQuantityInput | None = None
    pack_unit: Unit | None = None
    nutrients: NutrientValues | None = None

    check_not_null = field_validator("barcode", "ingredient_id", "nutrition_basis")(not_null)
