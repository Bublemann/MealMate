"""Products: barcodes linked to an ingredient (ING-04, BAR-04), the barcode lookup with its
Open Food Facts proposal (BAR-02, BAR-03) and pending updates (BAR-06)."""

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
)

from app.domain.catalog import (
    BARCODE_INPUT_MAX_LENGTH,
    PACK_QUANTITY_MAX,
    PRODUCT_BRAND_MAX_LENGTH,
    PRODUCT_FIELDS,
    PRODUCT_NAME_MAX_LENGTH,
    PRODUCT_QUANTITY_TEXT_MAX_LENGTH,
    check_text,
)
from app.domain.units import Unit
from app.schemas.ingredients import BaseUnitName, IdInput, IngredientSummary, not_null
from app.schemas.nutrition import NutrientValues
from app.schemas.users import UserRef

ProductSource = Literal["off", "manual"]
LookupSource = Literal["db", "off", "none"]

if TYPE_CHECKING:
    ProductField = str
else:
    # `nutrition_basis`, `name`, ..., `nutrients.kcal`, ...: generated from the registry.
    ProductField = Literal[PRODUCT_FIELDS]


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


class PendingUpdateField(BaseModel):
    """A user-edited field for which Open Food Facts now has another value: `current` is the
    product's value, `proposed` the new one (a text, a number or null)."""

    field: ProductField
    current: str | float | None
    proposed: str | float | None


class PendingUpdate(BaseModel):
    """Newer Open Food Facts values for user-edited fields (BAR-06), shown as "Open Food Facts
    has newer values: kcal 165 → 158 [Apply] [Ignore]". `off_last_modified_at` is when the
    product was last changed on Open Food Facts."""

    fields: list[PendingUpdateField]
    off_last_modified_at: datetime | None


class Product(BaseModel):
    """`nutrients` are per 100 g or 100 ml (`nutrition_basis`, always the ingredient's base
    unit). `user_edited_fields` names the fields a user typed or changed (`name`,
    `nutrients.kcal`, ...); Open Food Facts never overwrites them (BAR-04). Products with
    `source` off are refreshed from Open Food Facts; `pending_update` then holds newer values
    for user-edited fields (BAR-06)."""

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
    user_edited_fields: list[ProductField]
    fetched_at: datetime | None
    pending_update: PendingUpdate | None
    created_by: UserRef | None
    updated_by: UserRef | None
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    """A product entered by hand, or saved from an Open Food Facts proposal. The barcode is
    EAN-13, EAN-8, UPC-A or UPC-E with a valid check digit (spaces are ignored); it is stored as
    EAN-13 (UPC-A with a leading 0, UPC-E expanded first), an EAN-8 as it is.
    `nutrition_basis` defaults to the ingredient's base unit and must match it (409
    `product.basis_mismatch`).

    - `source` manual (the default): every field given is marked user-edited.
    - `source` off: the values come from the lookup's proposal (possibly corrected), with its
      `off_last_modified_at`; only the `edited_fields` (those the user changed compared with
      the proposal) are marked user-edited, the others are refreshed from Open Food Facts
      (BAR-04, BAR-05). `edited_fields` and `off_last_modified_at` are ignored for manual
      products."""

    barcode: BarcodeInput
    ingredient_id: IdInput
    nutrition_basis: BaseUnitName | None = None
    name: ProductNameInput | None = None
    brand: BrandInput | None = None
    quantity_text: QuantityTextInput | None = None
    pack_quantity: PackQuantityInput | None = None
    pack_unit: Unit | None = None
    nutrients: NutrientValues | None = None
    source: ProductSource = "manual"
    off_last_modified_at: AwareDatetime | None = None
    edited_fields: list[ProductField] | None = Field(default=None, max_length=len(PRODUCT_FIELDS))


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


class ProductProposal(BaseModel):
    """A product from Open Food Facts, validated and cleaned (BAR-10) but not saved.

    `name` is in the user's language if Open Food Facts has it. `nutrition_basis` is null when
    Open Food Facts gives no values per 100 g or 100 ml; the nutrients are then all unknown and
    the basis is the chosen ingredient's base unit. `category_key` is a guessed category
    (`/api/categories` key) for a new ingredient, or null. Values that are not plausible are
    dropped (null)."""

    name: str | None
    brand: str | None
    quantity_text: str | None
    pack_quantity: float | None
    pack_unit: Unit | None
    nutrition_basis: BaseUnitName | None
    nutrients: NutrientValues
    category_key: str | None
    off_last_modified_at: datetime | None


class ProductLookup(BaseModel):
    """The result of a barcode lookup (BAR-02, BAR-03), our own database first:

    - `found_in` db: `product` and its `ingredient` (go straight to it);
    - `found_in` off: the `proposal` and name-matched `suggestions` for "Which ingredient is
      this?"; nothing is saved yet;
    - `found_in` none: unknown to Open Food Facts, or `off_unavailable` when it could not be
      asked (slow or unreachable); the user enters the values.

    `barcode` is the canonical form (EAN-13, or EAN-8) to save the product with."""

    barcode: str
    found_in: LookupSource
    product: Product | None
    ingredient: IngredientSummary | None
    proposal: ProductProposal | None
    suggestions: list[IngredientSummary]
    off_unavailable: bool
