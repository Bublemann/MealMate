"""Notices (D-51): what happened to a user's data that they should learn of, unread until they
dismiss it. The backend sends a kind and its parameters, never text; the frontend words them
(I18N-03)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# Plain alias (not a `type` statement) so the OpenAPI schema inlines the literal.
# `recurring_item.ingredient_deleted`: an admin deleted an ingredient the user kept as a
# recurring item (ING-05); params `name` and `brand` (or null) as they were.
NoticeKind = Literal["recurring_item.ingredient_deleted"]


class Notice(BaseModel):
    """An unread notice of the caller's."""

    id: str
    kind: NoticeKind
    params: dict[str, str | None]
    created_at: datetime


class NoticeList(BaseModel):
    """The caller's unread notices, newest first, and how many there are (the count on the
    Settings tab, UI-07)."""

    notices: list[Notice]
    count: int
