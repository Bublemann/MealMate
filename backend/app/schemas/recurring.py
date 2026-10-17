"""Recurring items (LIST-16, D-42): ingredients a user, or a couple together, buys again and
again, each with its interval, last purchase and due date.

`schemas.lists` must not import this module (it imports `schemas.lists`).
"""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.domain.recurring import WEEKS_MAX, WEEKS_MIN, IntervalUnit
from app.schemas.ingredients import IdInput, IngredientSummary, not_null
from app.schemas.lists import DisplayAmountOut

IntervalWeeksInput = Annotated[int, Field(ge=WEEKS_MIN, le=WEEKS_MAX)]


class RecurringInterval(BaseModel):
    """The interval an item is due after, as the app shows it (MNT-02): below a week in days,
    else in whole weeks rounded to the nearest. `automatic` while it adapts to the purchases
    ("alle ~4 Wochen"); off when it was set by hand ("alle 4 Wochen")."""

    value: int
    unit: IntervalUnit
    automatic: bool


class RecurringItem(BaseModel):
    """An item of the caller's set. It is due from `due_on` on: the last purchase plus the
    interval, in calendar days of the instance's time zone. `days_until_due` counts from today
    (0 "fällig heute", 1 "fällig morgen", -3 "fällig seit 3 Tagen"). `interval_weeks` is the
    set interval for the edit pop-up. `last_amount` is the last purchase's amount, only while
    its unit fits the ingredient's base unit (REF-02)."""

    id: str
    ingredient: IngredientSummary
    interval: RecurringInterval
    interval_weeks: int
    last_purchased_on: date
    due_on: date
    days_until_due: int
    due: bool
    last_amount: DisplayAmountOut | None


class RecurringItemList(BaseModel):
    """The caller's set (their couple's while in one, else their own), sorted by due date and
    then by the ingredient's name, and how many items are due."""

    items: list[RecurringItem]
    due_count: int


class RecurringItemCreate(BaseModel):
    """Make an ingredient recurring: every `interval_weeks` (1 to 52), last bought on
    `last_purchased_on` (today if left out; not in the future, at most 730 days back:
    422 `out_of_range`). An ingredient already in the set is 422 `taken`, an unknown one
    `invalid`. The interval adapts automatically from the second purchase on."""

    ingredient_id: IdInput
    interval_weeks: IntervalWeeksInput
    last_purchased_on: date | None = None


class RecurringItemUpdate(BaseModel):
    """Only the fields that are sent change; null is refused (422 `invalid`). A new
    `interval_weeks` sets the interval by hand. `automatic` true lets it adapt again, with the
    set interval serving until two intervals are measured; false alone keeps the interval that
    serves now, as set by hand. `last_purchased_on` corrects the last purchase date, within
    the same range as on create."""

    interval_weeks: IntervalWeeksInput | None = None
    automatic: bool | None = None
    last_purchased_on: date | None = None

    check_not_null = field_validator("interval_weeks", "automatic", "last_purchased_on")(not_null)
