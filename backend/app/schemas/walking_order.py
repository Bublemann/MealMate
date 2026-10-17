"""The walking order of a couple or a user without one (REF-01, D-48)."""

from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.ingredients import IdInput
from app.schemas.reference import CategoryNames


class WalkingOrderCategory(BaseModel):
    """A category that isn't deleted, *Uncategorized* included, shown by its name in the UI
    language (`names`). `new`: an admin added it after the own order was saved, so it went to
    the end; it stays new until it is moved."""

    id: str
    key: str | None
    names: CategoryNames
    new: bool


class WalkingOrder(BaseModel):
    """The caller's walking order: their couple's while in one, else their own. While
    `follows_admin` ("Reihenfolge der Verwaltung übernehmen") it is the admins' order and follows
    their changes; otherwise it is the own order. `categories` lists every category that isn't
    deleted in that order."""

    follows_admin: bool
    categories: list[WalkingOrderCategory]


class WalkingOrderSave(BaseModel):
    """An own order: every category that isn't deleted exactly once, *Uncategorized* included,
    in the new order. `moved_id` names the category the user moved, which is no longer new;
    left out or null when the switch was turned off without a move."""

    category_ids: Annotated[list[IdInput], Field(max_length=100)]
    moved_id: IdInput | None = None
