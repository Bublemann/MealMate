"""Shopping lists: summaries, the detail with meals, aggregated lines and extra items, and
the inputs that change them (LIST-01..10, LIST-13..15, AGG, VIS-03/06, CPL-02/03)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, StringConstraints, field_validator

from app.domain.aggregation import SourceKind
from app.domain.catalog import check_text
from app.domain.lists import (
    AMOUNT_TEXT_MAX_LENGTH,
    EXTRA_TEXT_MAX_LENGTH,
    LIST_NAME_MAX_LENGTH,
    DetachedReason,
    ListStatus,
)
from app.domain.units import Unit
from app.schemas.ingredients import IdInput, not_null
from app.schemas.meals import AmountInput, ServingsInput
from app.schemas.products import blank_to_none
from app.schemas.users import UserRef

# Plain aliases (not `type` statements) so the OpenAPI schema inlines the literals.
ListScope = Literal["mine", "others"]
LineKind = Literal["ingredient", "text"]
# Room for the longest UUID spelling Python accepts (`urn:uuid:` and 36 characters).
CLIENT_ID_MAX_LENGTH = 45


def _canonical_uuid(value: str) -> str:
    """Any spelling of a UUID, stored in its canonical lowercase form."""
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise ValueError("not a UUID") from None


ListNameInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=LIST_NAME_MAX_LENGTH),
    AfterValidator(check_text),
    AfterValidator(blank_to_none),
]
ExtraTextInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=EXTRA_TEXT_MAX_LENGTH),
    AfterValidator(check_text),
]
AmountTextInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=AMOUNT_TEXT_MAX_LENGTH),
    AfterValidator(check_text),
    AfterValidator(blank_to_none),
]
ClientIdInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=CLIENT_ID_MAX_LENGTH),
    AfterValidator(_canonical_uuid),
]


class DisplayAmountOut(BaseModel):
    """An amount rounded for display (AGG-04); the frontend only formats it for the locale."""

    value: float
    unit: Unit


class ListMealEntry(BaseModel):
    """A meal on a list with its servings (LIST-04).

    A meal the viewer may not see is `private`: only its servings are shown, as "Private meal
    (N servings)" (VIS-06). `detached` says why a meal is no longer available (LIST-15); it
    keeps contributing its frozen rows until it is removed, and has no `meal_id` (its `name` is
    the one it had). `meal_servings` is what the meal's rows are written for; the rows are
    scaled by `servings ÷ meal_servings`. `thumb_url` is a signed URL of the photo's thumbnail.
    """

    id: str
    meal_id: str | None
    name: str | None
    private: bool
    owner: UserRef | None
    thumb_url: str | None
    servings: int
    meal_servings: int
    detached: DetachedReason | None


class LineSource(BaseModel):
    """Where a line comes from (LIST-08): a meal on the list (`list_meal_id`, its `servings`;
    `meal_name` null and `private` if the viewer may not see it, VIS-06) or an extra item
    (`extra_id`, with its own amount and unit, or its free-text `amount_text`)."""

    kind: SourceKind
    list_meal_id: str | None
    extra_id: str | None
    meal_name: str | None
    private: bool
    servings: int | None
    amount: float | None
    unit: Unit | None
    amount_text: str | None


class ListLine(BaseModel):
    """An aggregated line (AGG), identified by `key`: `i:<ingredient_id>` for an ingredient,
    `x:<extra_id>` for a free-text item.

    `amounts` are the display amounts, shown joined ("500 g + 2 Stk."); `has_unspecified` means
    a part without an amount ("+ some", or "some" alone). A free-text line has no amounts and
    shows its `amount_text` as it is. `hidden` lines were removed for this list (LIST-07) and
    belong in the collapsed "Removed" section. `category_id` groups the lines; they come
    sorted by category order and name (AGG-05).
    """

    key: str
    kind: LineKind
    ingredient_id: str | None
    name: str
    category_id: str
    amounts: list[DisplayAmountOut]
    has_unspecified: bool
    amount_text: str | None
    hidden: bool
    sources: list[LineSource]


class ExtraItem(BaseModel):
    """An extra item (LIST-06): linked to an ingredient (`ingredient_id`, optional `amount`
    and `unit`) or free text (`text`, optional `amount_text`, `category_id`)."""

    id: str
    ingredient_id: str | None
    text: str | None
    amount: float | None
    unit: Unit | None
    amount_text: str | None
    category_id: str | None
    added_by: UserRef | None
    created_at: datetime


class ListDetail(BaseModel):
    """A list as its viewer sees it. `is_owner` and `can_edit` say what the viewer may do:
    editors change the name, meals, servings, extra items and hidden lines; only the owner
    deletes the list and changes `shared_with_partner` (CPL-02/03). The display name is
    `<name or the translated default> (<created_at as a date>)` (LIST-02); the reminder is
    `reminder.<reminder_seed % 10 + 1>` (LIST-14)."""

    id: str
    name: str | None
    status: ListStatus
    version: int
    created_at: datetime
    updated_at: datetime
    owner: UserRef
    is_owner: bool
    can_edit: bool
    shared_with_partner: bool
    reminder_seed: int
    meals: list[ListMealEntry]
    lines: list[ListLine]
    extra_items: list[ExtraItem]


class ListSummary(BaseModel):
    """A list on the Lists home (UI-02); `line_count` counts the lines that are not hidden."""

    id: str
    name: str | None
    status: ListStatus
    created_at: datetime
    updated_at: datetime
    owner: UserRef
    is_owner: bool
    can_edit: bool
    shared_with_partner: bool
    meal_count: int
    line_count: int


class ListCopyResult(BaseModel):
    """The new draft, and how many meals were left out because they no longer exist or the
    copier may not see them (VIS-03/06)."""

    list: ListDetail
    left_out: int


class ListCreate(BaseModel):
    """`name`: at most 60 characters; empty or left out shows the translated default."""

    name: ListNameInput | None = None


class ListUpdate(BaseModel):
    """Only the fields that are sent change. `name` null or empty goes back to the default
    name (editors). `shared_with_partner` is the owner's switch (CPL-02); it can only be turned
    on while the owner is in a couple (422 `invalid` otherwise), and null is refused."""

    name: ListNameInput | None = None
    shared_with_partner: bool | None = None

    check_not_null = field_validator("shared_with_partner")(not_null)


class ListMealAdd(BaseModel):
    """Add a meal you can see (LIST-03). `servings` (1 to 99) defaults to the meal's own; if
    the meal is already on the list, its servings rise by that many (LIST-04), to at most
    99."""

    meal_id: IdInput
    servings: ServingsInput | None = None


class ListMealUpdate(BaseModel):
    servings: ServingsInput


class ExtraItemCreate(BaseModel):
    """Exactly one of `ingredient_id` and `text` (LIST-06).

    - linked (`ingredient_id`): optional `amount` (0 < x ≤ 100000) and `unit`; an amount
      without a unit counts as pieces, a unit without an amount is refused; no `amount_text`
      or `category_id`;
    - free text (`text`, 1 to 80 characters): optional `amount_text` (at most 30 characters)
      and `category_id` (default: *Other*); no `amount` or `unit`.

    `id` may be any UUID chosen by the client; sending the same id again changes nothing.
    """

    id: ClientIdInput | None = None
    ingredient_id: IdInput | None = None
    amount: AmountInput | None = None
    unit: Unit | None = None
    text: ExtraTextInput | None = None
    amount_text: AmountTextInput | None = None
    category_id: IdInput | None = None


class ExtraItemUpdate(BaseModel):
    """Only the fields that are sent change, with the rules of `ExtraItemCreate`; the kind of
    item cannot change (422 `invalid` for the other kind's fields). Null clears the amount,
    unit or amount text, and is refused for `ingredient_id`, `text` and `category_id`."""

    ingredient_id: IdInput | None = None
    amount: AmountInput | None = None
    unit: Unit | None = None
    text: ExtraTextInput | None = None
    amount_text: AmountTextInput | None = None
    category_id: IdInput | None = None

    check_not_null = field_validator("ingredient_id", "text", "category_id")(not_null)
