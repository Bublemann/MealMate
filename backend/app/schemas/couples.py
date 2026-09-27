"""Couples and couple requests (CPL-01)."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.schemas.users import UserRef


class CoupleRequest(BaseModel):
    id: str
    from_user: UserRef
    to_user: UserRef
    created_at: datetime


class CoupleState(BaseModel):
    """The own couple (`partner`, accepted at `since`) and pending requests."""

    partner: UserRef | None
    since: datetime | None
    outgoing: CoupleRequest | None
    incoming: list[CoupleRequest]


class CoupleRequestCreate(BaseModel):
    user_id: Annotated[str, StringConstraints(min_length=1, max_length=36)]
