"""Meals, their ingredient rows, photo and nutrition (MEAL-01..10, NUT-03..05, VIS-05)."""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator

from app.domain.catalog import TAG_NAME_MAX_LENGTH, check_name, check_text
from app.domain.meals import (
    INSTRUCTIONS_MAX_LENGTH,
    MEAL_NAME_MAX_LENGTH,
    MEAL_ROWS_MAX,
    MEAL_TAGS_MAX,
    ROW_AMOUNT_MAX,
    ROW_NOTE_MAX_LENGTH,
    SERVINGS_MAX,
    SERVINGS_MIN,
    SOURCE_URL_MAX_LENGTH,
    check_instructions,
    check_source_url,
)
from app.domain.nutrition import MissingReason
from app.domain.units import Unit
from app.schemas.ingredients import IdInput, IngredientSummary, not_null
from app.schemas.nutrition import NutrientValues
from app.schemas.products import blank_to_none
from app.schemas.reference import Cuisine, Tag
from app.schemas.users import UserRef


def _source_url(url: str) -> str | None:
    """An empty link is stored as null; anything else must be a valid source link."""
    return check_source_url(url) if url else None


MealNameInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MEAL_NAME_MAX_LENGTH),
    AfterValidator(check_name),
]
InstructionsInput = Annotated[
    str,
    StringConstraints(max_length=INSTRUCTIONS_MAX_LENGTH),
    AfterValidator(check_instructions),
    AfterValidator(str.strip),
    AfterValidator(blank_to_none),
]
SourceUrlInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=SOURCE_URL_MAX_LENGTH),
    AfterValidator(_source_url),
]
ServingsInput = Annotated[int, Field(ge=SERVINGS_MIN, le=SERVINGS_MAX)]
TagNameInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=TAG_NAME_MAX_LENGTH),
    AfterValidator(check_name),
]
TagsInput = Annotated[list[TagNameInput], Field(max_length=MEAL_TAGS_MAX)]
AmountInput = Annotated[float, Field(gt=0, le=ROW_AMOUNT_MAX, allow_inf_nan=False)]
NoteInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=ROW_NOTE_MAX_LENGTH),
    AfterValidator(check_text),
    AfterValidator(blank_to_none),
]


class MealPhoto(BaseModel):
    """Signed URLs of the photo and its thumbnail; they expire after 1 to 2 hours (VIS-05)."""

    url: str
    thumb_url: str


class MealIngredientRow(BaseModel):
    """An ingredient row; `amount` and `unit` are both null for e.g. "salt, to taste"."""

    id: str
    position: int
    ingredient: IngredientSummary
    amount: float | None
    unit: Unit | None
    note: str | None


class MealNutritionMissing(BaseModel):
    """Why a row does not (fully) count: no amount, an amount that cannot be converted to the
    ingredient's base unit, or an unknown value for `nutrient` (NUT-04)."""

    ingredient_id: str
    ingredient_name: str
    reason: MissingReason
    nutrient: str | None


class MealNutrition(BaseModel):
    """Totals over the rows that could be counted (NUT-03); a nutrient is null only if nothing
    contributed to it. `incomplete` if anything is `missing` (NUT-04); `estimate` if spoons of
    a g-based ingredient without density were counted as 1 g/ml (NUT-05). The totals are not
    bounded by the per-100 maximums of `NutrientValues`."""

    per_meal: NutrientValues
    per_serving: NutrientValues
    incomplete: bool
    estimate: bool
    missing: list[MealNutritionMissing]


class MealBasedOn(BaseModel):
    """The original of a copy, shown as "based on X by Y" (MEAL-08) while the original exists
    and the viewer may see it."""

    meal_id: str
    name: str
    owner: UserRef


class Meal(BaseModel):
    """A meal as its viewer sees it; `is_owner` tells whether they may edit it (VIS-04)."""

    id: str
    name: str
    owner: UserRef
    is_owner: bool
    instructions: str | None
    source_url: str | None
    servings: int
    cuisine: Cuisine | None
    tags: list[Tag]
    photo: MealPhoto | None
    ingredients: list[MealIngredientRow]
    nutrition: MealNutrition
    based_on: MealBasedOn | None
    created_at: datetime
    updated_at: datetime


class MealSummary(BaseModel):
    """A meal in the meal list; `thumb_url` is a signed URL of the photo's thumbnail."""

    id: str
    name: str
    owner: UserRef
    cuisine: Cuisine | None
    tags: list[Tag]
    servings: int
    thumb_url: str | None
    updated_at: datetime


class MealIngredientInput(BaseModel):
    """`amount`: 0 < x ≤ 100000. An amount without a unit counts as pieces; a unit without an
    amount is refused (`ingredients.<i>.amount` `required`). An empty note is stored as null."""

    ingredient_id: IdInput
    amount: AmountInput | None = None
    unit: Unit | None = None
    note: NoteInput | None = None


class MealCreate(BaseModel):
    """Only the name is required (MEAL-01).

    - `instructions`: plain text with line breaks, at most 10000 characters;
    - `source_url`: an `http(s)` URL with a host and without user info (MEAL-05);
    - `servings`: 1 to 99;
    - `tags`: at most 10 names of 1 to 30 characters; existing tags are reused ignoring case and
      umlauts, missing ones are created;
    - `ingredients`: at most 100 rows, in order.

    Empty texts are stored as null.
    """

    name: MealNameInput
    instructions: InstructionsInput | None = None
    source_url: SourceUrlInput | None = None
    servings: ServingsInput = 1
    cuisine_id: IdInput | None = None
    tags: TagsInput = Field(default_factory=list)
    ingredients: Annotated[list[MealIngredientInput], Field(max_length=MEAL_ROWS_MAX)] = Field(
        default_factory=list
    )


class MealUpdate(BaseModel):
    """Only the fields that are sent change, with the rules of `MealCreate`. An explicit null
    clears the instructions, source link or cuisine, and is refused for the other fields (422
    `invalid`). `tags` and `ingredients` replace the whole list."""

    name: MealNameInput | None = None
    instructions: InstructionsInput | None = None
    source_url: SourceUrlInput | None = None
    servings: ServingsInput | None = None
    cuisine_id: IdInput | None = None
    tags: TagsInput | None = None
    ingredients: Annotated[list[MealIngredientInput], Field(max_length=MEAL_ROWS_MAX)] | None = None

    check_not_null = field_validator("name", "servings", "tags", "ingredients")(not_null)
