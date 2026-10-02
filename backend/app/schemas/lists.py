"""Shopping lists: summaries, the detail with meals, aggregated lines with their check state
and extra items, the inputs that change them, and the ops of shopping mode (LIST-01..15, AGG,
SHOP, SYNC-05/06, VIS-03/06, CPL-02/03)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    Field,
    RootModel,
    StringConstraints,
    field_validator,
)

from app.core.errors import ErrorCode
from app.domain.aggregation import SourceKind
from app.domain.catalog import check_text
from app.domain.lists import (
    AMOUNT_TEXT_MAX_LENGTH,
    EXTRA_TEXT_MAX_LENGTH,
    LINE_KEY_MAX_LENGTH,
    LIST_NAME_MAX_LENGTH,
    OPS_MAX,
    DetachedReason,
    ListStatus,
)
from app.domain.units import Unit
from app.schemas.ingredients import IdInput, blank_to_none, not_null
from app.schemas.meals import AmountInput, ServingsInput
from app.schemas.users import UserRef

# Plain aliases (not `type` statements) so the OpenAPI schema inlines the literals.
LineKind = Literal["ingredient", "text"]
OpStatus = Literal["applied", "duplicate", "rejected"]
# Room for the longest UUID spelling Python accepts (`urn:uuid:` and 36 characters).
CLIENT_ID_MAX_LENGTH = 45
CATEGORY_KEY_MAX_LENGTH = 40


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


class LineNeedsMore(BaseModel):
    """Why a line that was checked off is unchecked again (LIST-12): `grown` holds the
    differences, rounded for display ("+300 g", "+2 Stk."); `new_unit`: an amount in a unit
    of another kind appeared; `new_unspecified`: a part without an amount appeared ("+ some");
    `changed`: the free-text item's text or amount was edited."""

    grown: list[DisplayAmountOut]
    new_unit: bool
    new_unspecified: bool
    changed: bool


class ListLine(BaseModel):
    """An aggregated line (AGG), identified by `key`: `i:<ingredient_id>` for an ingredient,
    `x:<extra_id>` for a free-text item.

    `amounts` are the display amounts, shown joined ("500 g + 2 Stk."); `has_unspecified` means
    a part without an amount ("+ some", or "some" alone). A free-text line has no amounts and
    shows its `amount_text` as it is. `hidden` lines were removed for this list (LIST-07) and
    belong in the collapsed "Removed" section. `category_id` groups the lines; they come
    sorted by category order and name (AGG-05).

    Check state (shopping and done lists; always unchecked in a draft): `checked` with the
    time of the tap (`checked_at`) and who checked it (`checked_by`, SHOP-01). A checked line
    that needs more since is reported unchecked, with `needs_more` saying why (LIST-12). `new`:
    the line appeared after shopping started (LIST-12).
    """

    key: str
    kind: LineKind
    ingredient_id: str | None
    name: str
    brand: str | None
    category_id: str
    amounts: list[DisplayAmountOut]
    has_unspecified: bool
    amount_text: str | None
    hidden: bool
    sources: list[LineSource]
    checked: bool
    checked_at: datetime | None
    checked_by: UserRef | None
    new: bool
    needs_more: LineNeedsMore | None


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
    `reminder.<reminder_seed % 10 + 1>` (LIST-14). `shopping_started_at` and `finished_at`
    are set once shopping started and while the list is done (LIST-10)."""

    id: str
    name: str | None
    status: ListStatus
    version: int
    created_at: datetime
    updated_at: datetime
    shopping_started_at: datetime | None
    finished_at: datetime | None
    owner: UserRef
    is_owner: bool
    can_edit: bool
    shared_with_partner: bool
    reminder_seed: int
    meals: list[ListMealEntry]
    lines: list[ListLine]
    extra_items: list[ExtraItem]


class ListSummary(BaseModel):
    """A list in the list feed (UI-02); `line_count` counts the lines that are not hidden.
    `finished_at` is the day a done list was bought (SHOP-05)."""

    id: str
    name: str | None
    status: ListStatus
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    owner: UserRef
    is_owner: bool
    can_edit: bool
    shared_with_partner: bool
    meal_count: int
    line_count: int


class ListFeedPage(BaseModel):
    """A page of the list feed (UI-02): up to 30 lists, newest created first (ties by id).
    `next_cursor` asks for the next page (`GET /api/lists?cursor=`); null on the last one."""

    lists: list[ListSummary]
    next_cursor: str | None


class ListCopyResult(BaseModel):
    """The new draft, and how many meals were left out because they no longer exist or the
    copier may not see them (VIS-03/06, SHOP-06)."""

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


# --- ops (plan § 5.8, SYNC-05/06) -------------------------------------------------------------


class LineCheckPayload(BaseModel):
    """Check a line off or uncheck it. `line_key` as in `ListLine.key`; a key in another
    format is rejected (`common.validation`), a key without a line right now is accepted."""

    line_key: Annotated[str, StringConstraints(max_length=LINE_KEY_MAX_LENGTH)]
    checked: bool


class ExtraAddPayload(BaseModel):
    """Add a free-text extra item with the client's id (UUID), in the category `category_id`;
    left out or unknown: *Other*. App versions from before D-31 send the category's `key` as
    `category_key` instead, which is still accepted."""

    extra_id: ClientIdInput
    text: ExtraTextInput
    amount_text: AmountTextInput | None = None
    category_id: IdInput | None = None
    category_key: Annotated[str, StringConstraints(max_length=CATEGORY_KEY_MAX_LENGTH)] | None = (
        None
    )


class ExtraUpdatePayload(BaseModel):
    """Change a free-text extra item's text, and its `amount_text` if sent (null clears it)."""

    extra_id: ClientIdInput
    text: ExtraTextInput
    amount_text: AmountTextInput | None = None


class ExtraDeletePayload(BaseModel):
    extra_id: ClientIdInput


class ListFinishPayload(BaseModel):
    """No fields."""


class _OpBase(BaseModel):
    """`op_id`: a UUID chosen by the client (UUIDv7), unique per action, so sending it again
    has no effect (SYNC-05). `at`: when the action happened on the client, with a time zone
    (the last tap wins, SYNC-06)."""

    op_id: ClientIdInput
    at: AwareDatetime


class LineCheckOp(_OpBase):
    """Last write wins by `at` (clamped to at most 5 minutes after the server's time), ties by
    the higher `op_id`; a losing op is `applied` without effect. While shopping; on a done list
    only if `at` is not after `finished_at` (else `list.done`); not in a draft, nor with an `at`
    more than 5 minutes before `shopping_started_at` (`list.not_shopping`). An `at` that is out
    of range in UTC is rejected (`common.validation`)."""

    type: Literal["line.check"]
    payload: LineCheckPayload


class ExtraAddOp(_OpBase):
    """In a draft or while shopping (`list.done` otherwise). An `extra_id` already on this list
    is a `duplicate`; one on another list is rejected (`extra.id_taken`)."""

    type: Literal["extra.add"]
    payload: ExtraAddPayload


class ExtraUpdateOp(_OpBase):
    """In a draft or while shopping. A deleted item stays deleted (applied without effect,
    delete wins); an unknown id is rejected (`common.not_found`), a linked item too
    (`common.validation`)."""

    type: Literal["extra.update"]
    payload: ExtraUpdatePayload


class ExtraDeleteOp(_OpBase):
    """In a draft or while shopping; an item that is already deleted: applied without
    effect."""

    type: Literal["extra.delete"]
    payload: ExtraDeletePayload


class ListFinishOp(_OpBase):
    """Finish shopping (SHOP-04): the list is done, `finished_at` is `at` (but not before
    `shopping_started_at` nor after the server's time). Already done: applied without effect;
    a draft: `list.not_shopping`; an `at` out of range in UTC: `common.validation`."""

    type: Literal["list.finish"]
    payload: ListFinishPayload


class Op(
    RootModel[
        Annotated[
            LineCheckOp | ExtraAddOp | ExtraUpdateOp | ExtraDeleteOp | ListFinishOp,
            Field(discriminator="type"),
        ]
    ]
):
    """One action of shopping mode, by `type`, with its typed `payload`."""


class OpsRequest(BaseModel):
    """1 to 100 ops, applied in this order in one transaction."""

    ops: Annotated[list[Op], Field(min_length=1, max_length=OPS_MAX)]


class OpResult(BaseModel):
    """What became of an op: `applied` (also when it had no effect, e.g. an older check-off
    than the stored one), `duplicate` (already processed; nothing happened again) or `rejected`
    with an error `code` (the op may succeed later, e.g. after the list is reopened)."""

    op_id: str
    status: OpStatus
    code: ErrorCode | None


class OpsResponse(BaseModel):
    """One result per op, in order, and the list afterwards."""

    results: list[OpResult]
    list: ListDetail


class ListsSync(BaseModel):
    """The local copy for offline use (SYNC-02): every list the viewer can edit that is a
    draft or being shopped (their own and those their partner shares with them), each exactly
    as `GET /api/lists/{id}` shows it, most recently edited first. A list that is missing from
    it is gone from the copy (deleted, done, or access lost; SYNC-10). `generated_at` is the
    server time of the answer; it is not part of the `ETag`, which covers `lists` only."""

    lists: list[ListDetail]
    generated_at: datetime
