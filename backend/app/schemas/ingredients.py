"""Ingredients (ING-01..06, NUT-02), their barcode and Open Food Facts data (BAR-02..10).

There is one kind of ingredient: typed by hand, with a brand, or taken from Open Food Facts with
its barcode. It is counted in its base unit: g, ml or pieces (D-32). Nutrients are the
ingredient's own values per 100 g, or per 100 ml for an ml ingredient.
"""

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
from pydantic.json_schema import SkipJsonSchema
from pydantic_core import PydanticCustomError

from app.domain.catalog import (
    BARCODE_INPUT_MAX_LENGTH,
    BRAND_MAX_LENGTH,
    INGREDIENT_NAME_MAX_LENGTH,
    OFF_FIELDS,
    PACK_QUANTITY_MAX,
    PIECE_WEIGHT_MAX_G,
    QUANTITY_TEXT_MAX_LENGTH,
    check_name,
    check_text,
)
from app.domain.units import Unit
from app.schemas.nutrition import NutrientValues
from app.schemas.users import UserRef

# Plain aliases (not `type` statements) so the OpenAPI schema inlines them.
BaseUnitName = Literal["g", "ml", "piece"]
# What Open Food Facts gives nutrients per: 100 g or 100 ml.
NutritionBasisName = Literal["g", "ml"]
IngredientSource = Literal["manual", "off"]
LookupSource = Literal["db", "off", "none"]

if TYPE_CHECKING:
    IngredientField = str
else:
    # `name`, `brand`, ..., `nutrients.kcal`, ...: generated from the registry.
    IngredientField = Literal[OFF_FIELDS]


def base_unit_name(value: str) -> BaseUnitName:
    """A stored base unit as the API names it."""
    match value:
        case "ml":
            return "ml"
        case "piece":
            return "piece"
        case _:
            return "g"


def blank_to_none(text: str) -> str | None:
    """Optional texts left empty (after trimming) are stored as null."""
    return text or None


def not_null[T](value: T | None) -> T:
    """For update fields that cannot be empty: leaving one out keeps it, an explicit null is
    refused (field code `invalid`) instead of being ignored."""
    if value is None:
        raise PydanticCustomError("not_null", "may not be null")
    return value


IdInput = Annotated[str, StringConstraints(min_length=1, max_length=36)]
IngredientNameInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=INGREDIENT_NAME_MAX_LENGTH),
    AfterValidator(check_name),
]
PieceWeightInput = Annotated[float, Field(gt=0, le=PIECE_WEIGHT_MAX_G, allow_inf_nan=False)]
BarcodeInput = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=BARCODE_INPUT_MAX_LENGTH)
]
BrandInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=BRAND_MAX_LENGTH),
    AfterValidator(check_text),
    AfterValidator(blank_to_none),
]
QuantityTextInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=QUANTITY_TEXT_MAX_LENGTH),
    AfterValidator(check_text),
    AfterValidator(blank_to_none),
]
PackQuantityInput = Annotated[float, Field(gt=0, le=PACK_QUANTITY_MAX, allow_inf_nan=False)]


class IngredientSummary(BaseModel):
    """A search result, list entry or meal row's ingredient. It is shown as `name` with the
    `brand` in brackets when there is one ("Milch (Weihenstephan)"); `barcode` is set for
    scanned ingredients."""

    id: str
    name: str
    brand: str | None
    barcode: str | None
    source: IngredientSource
    category_id: str
    base_unit: BaseUnitName


class PendingUpdateField(BaseModel):
    """A user-edited field for which Open Food Facts now has another value: `current` is the
    ingredient's value, `proposed` the new one (a text, a number or null)."""

    field: IngredientField
    current: str | float | None
    proposed: str | float | None


class PendingUpdate(BaseModel):
    """Newer Open Food Facts values for user-edited fields (BAR-06), shown as "Open Food Facts
    has newer values: kcal 165 → 158 [Apply] [Ignore]". `off_last_modified_at` is when the
    product was last changed on Open Food Facts."""

    fields: list[PendingUpdateField]
    off_last_modified_at: datetime | None


class IngredientUsage(BaseModel):
    """How many meals use the ingredient, and how many lists keep it in frozen rows or extra
    items (the references that block deleting it, ING-05)."""

    meals: int
    lists: int


class Ingredient(BaseModel):
    """An ingredient counted in `base_unit`, with its own nutrition (NUT-02; null is unknown,
    never 0) per 100 g, or per 100 ml for base unit ml. A `piece` ingredient's pieces count
    with `piece_weight_g` (NUT-05), which is null for the other base units (D-32).

    `source` off: taken from Open Food Facts by its `barcode` and refreshed from there
    (BAR-05); `user_edited_fields` names the fields a user changed (`name`, `nutrients.kcal`,
    ...), which a refresh never overwrites (BAR-04), and `pending_update` holds newer Open Food
    Facts values for them (BAR-06). `quantity_text`, `pack_quantity` and `pack_unit` are the
    pack size from Open Food Facts (information only, never user-edited, D-38). `created_by` /
    `updated_by` are null for a deleted user (ING-06).
    """

    id: str
    name: str
    brand: str | None
    barcode: str | None
    category_id: str
    base_unit: BaseUnitName
    piece_weight_g: float | None
    nutrients: NutrientValues
    quantity_text: str | None
    pack_quantity: float | None
    pack_unit: Unit | None
    source: IngredientSource
    user_edited_fields: list[IngredientField]
    off_last_modified_at: datetime | None
    fetched_at: datetime | None
    pending_update: PendingUpdate | None
    usage: IngredientUsage
    created_by: UserRef | None
    updated_by: UserRef | None
    created_at: datetime
    updated_at: datetime


class IngredientOffOrigin(BaseModel):
    """The ingredient's values come from an Open Food Facts proposal (a barcode lookup or the
    name search), possibly corrected: `off_last_modified_at` is the proposal's, and
    `edited_fields` the fields the user changed compared with it. Only those are marked
    user-edited; the others are refreshed from Open Food Facts (BAR-04, BAR-05)."""

    off_last_modified_at: AwareDatetime | None = None
    edited_fields: list[IngredientField] = Field(default_factory=list, max_length=len(OFF_FIELDS))


class IngredientCreate(BaseModel):
    """A new ingredient (ING-02), in one request also when it was scanned.

    `category_id` defaults to the *Other* category, `base_unit` to g. `piece_weight_g`:
    0 < x ≤ 10000, only for base unit `piece` (422 `invalid` otherwise, D-32). `nutrients` per
    100 g, or per 100 ml for base unit ml. The barcode is EAN-13, EAN-8, UPC-A or UPC-E with a
    valid check digit (spaces are ignored; 422 `invalid_format` otherwise) and stored as EAN-13
    (UPC-A with a leading 0, UPC-E expanded first), an EAN-8 as it is; a barcode another
    ingredient has is 409 `ingredient.barcode_taken`.

    With `off`, the ingredient is from Open Food Facts (`source` off, refreshed later) and needs
    its `barcode` (422 `required` without). Only then are `quantity_text`, `pack_quantity` and
    `pack_unit` taken, the pack size passed on from the proposal; without `off` they are refused
    (422 `invalid`), as nobody types in a pack size (D-38). Names need not be unique: the
    "similar ingredient exists" hint (`GET /api/ingredients/similar`) is only a hint.
    """

    name: IngredientNameInput
    brand: BrandInput | None = None
    barcode: BarcodeInput | None = None
    category_id: IdInput | None = None
    base_unit: BaseUnitName = "g"
    piece_weight_g: PieceWeightInput | None = None
    nutrients: NutrientValues | None = None
    quantity_text: QuantityTextInput | None = None
    pack_quantity: PackQuantityInput | None = None
    pack_unit: Unit | None = None
    off: IngredientOffOrigin | None = None


class IngredientUpdate(BaseModel):
    """Only the fields that are sent change (ING-01); an explicit null clears an optional one
    and is refused for the name, category and base unit (422 `invalid`). `nutrients` changes
    only the nutrients it contains (null clears one).

    On an ingredient from Open Food Facts, every Open Food Facts field sent (`name`, `brand` and
    the nutrients) becomes user-edited (BAR-04). The pack size (`quantity_text`, `pack_quantity`,
    `pack_unit`) comes only from Open Food Facts and is refused here, even as null (422
    `invalid`, D-38). A new barcode must be free (409
    `ingredient.barcode_taken`); clearing or changing the barcode of an ingredient from Open
    Food Facts makes it manual: a refresh by the new barcode would overwrite its values with
    another product's. The base unit may change freely; the values are not converted.
    Changing it to or from `piece` clears the piece weight, unless the change to `piece` sends
    one. A piece weight is only taken for an ingredient that is (or becomes) counted in pieces
    (422 `invalid` otherwise, D-32). A base-unit change that would leave amounts in meals or on
    drafts not fitting is refused (409 `ingredient.unit_mismatch`, D-33) unless
    `accept_unit_mismatch` is true (left out or null, it isn't); those amounts are then kept as
    they are and flagged.
    """

    name: IngredientNameInput | None = None
    brand: BrandInput | None = None
    barcode: BarcodeInput | None = None
    category_id: IdInput | None = None
    base_unit: BaseUnitName | None = None
    piece_weight_g: PieceWeightInput | None = None
    nutrients: NutrientValues | None = None
    accept_unit_mismatch: bool | None = None
    # Not part of the API: sent anyway (e.g. by an app from before D-38), the pack size is
    # refused by the service rather than ignored, so nobody believes it was saved.
    quantity_text: SkipJsonSchema[object] = None
    pack_quantity: SkipJsonSchema[object] = None
    pack_unit: SkipJsonSchema[object] = None

    check_not_null = field_validator("name", "category_id", "base_unit")(not_null)


class IngredientBarcodeLink(BaseModel):
    """Give an ingredient without a barcode the scanned one (the scanner's "already in
    MealMate"). Unlike an update, this never replaces a barcode: 409 `ingredient.has_barcode`
    if the ingredient has one, 409 `ingredient.barcode_taken` if another ingredient has it."""

    barcode: BarcodeInput


class IngredientMerge(BaseModel):
    """Merge the ingredient into `into_id` (ING-05). A merge across base units that would leave
    amounts of the ingredient not fitting the base unit of `into_id` is refused (409
    `ingredient.unit_mismatch`, D-33) unless `accept_unit_mismatch` is true (left out or null, it
    isn't)."""

    into_id: IdInput
    accept_unit_mismatch: bool | None = None


class ProductProposal(BaseModel):
    """A product from Open Food Facts, validated and cleaned (BAR-10) but not saved: the values
    to prefill the ingredient form with.

    `name` is in the user's language if Open Food Facts has it, cut at a word boundary to the
    60 characters of an ingredient name. `nutrition_basis` is null when Open Food Facts gives no
    values per 100 g or 100 ml; the nutrients are then all unknown. `category_key` is a guessed
    category (`/api/categories` key), or null. Values that are not plausible are dropped
    (null). `barcode` is the canonical form to save the ingredient with."""

    barcode: str
    name: str | None
    brand: str | None
    quantity_text: str | None
    pack_quantity: float | None
    pack_unit: Unit | None
    nutrition_basis: NutritionBasisName | None
    nutrients: NutrientValues
    category_key: str | None
    off_last_modified_at: datetime | None


class BarcodeLookup(BaseModel):
    """The result of a barcode lookup (BAR-02, BAR-03), our own ingredients first:

    - `found_in` db: the `ingredient` with this barcode (go straight to it, or pick it);
    - `found_in` off: Open Food Facts' `proposal`; nothing is saved until the user saves the
      prefilled ingredient form (`POST /api/ingredients` with `off`);
    - `found_in` none: unknown to Open Food Facts, or `off_unavailable` when it could not be
      asked (slow or unreachable); the user enters the values.

    `barcode` is the canonical form (EAN-13, or EAN-8) to save the ingredient with."""

    barcode: str
    found_in: LookupSource
    ingredient: Ingredient | None
    proposal: ProductProposal | None
    off_unavailable: bool


class OffSearchResult(BaseModel):
    """A product found by the Open Food Facts name search, as a `proposal` like the barcode
    lookup's. `in_mealmate`: an ingredient already has its barcode (`ingredient`), which can
    be picked instead of creating another one."""

    proposal: ProductProposal
    in_mealmate: bool
    ingredient: IngredientSummary | None


class OffSearchPage(BaseModel):
    """One page of up to 20 Open Food Facts products for the query `q`, sold in Germany, the
    most scanned first; `has_more` when there is a next `page`. Products without a valid
    barcode are left out, so a page may hold fewer."""

    q: str
    page: int
    results: list[OffSearchResult]
    has_more: bool
