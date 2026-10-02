"""Accounts as the API shows them: the own profile (`Me`), other users, sessions."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.domain.accounts import DISPLAY_NAME_MAX_LENGTH
from app.domain.lists import LIST_STATUSES, ListStatus

# Plain aliases (not `type` statements) so the OpenAPI schema inlines the literals.
Role = Literal["user", "admin"]
Language = Literal["de", "en"]
VisibilityScope = Literal["meals", "lists"]
# The parts of `FilterHidden`.
SavedFilter = Literal["meals", "lists", "list_states"]

DisplayNameInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH),
]
# Generous upper bound on any password field; the real rules are checked by the service.
PasswordInput = Annotated[str, StringConstraints(max_length=1024)]
UserIdList = Annotated[
    list[Annotated[str, StringConstraints(max_length=36)]], Field(max_length=500)
]
ListStatusList = Annotated[list[ListStatus], Field(max_length=len(LIST_STATUSES))]


class UserRef(BaseModel):
    """Another user as everyone sees them; deactivated users are shown with a note (ADM-02)."""

    id: str
    display_name: str
    deactivated: bool


class FilterHidden(BaseModel):
    """What this user's saved filters hide; empty shows everything. `meals` and `lists` are the
    users unticked in the user filter on Meals (MEAL-10) and on Lists (UI-02), `list_states` the
    states unticked in the state filter on Lists (UI-02)."""

    meals: UserIdList
    lists: UserIdList
    list_states: ListStatusList


class Me(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str
    role: Role
    language: Language
    meals_public: bool
    lists_public: bool
    filter_hidden: FilterHidden
    created_at: datetime


class MeUpdate(BaseModel):
    """Only the fields that are sent change (ACC-13, VIS-02, I18N-01)."""

    display_name: DisplayNameInput | None = None
    language: Language | None = None
    meals_public: bool | None = None
    lists_public: bool | None = None
    filter_hidden: FilterHidden | None = None


class PasswordChange(BaseModel):
    current_password: PasswordInput
    new_password: PasswordInput


class SessionInfo(BaseModel):
    """A logged-in device; `current` is the one making this request (ACC-09)."""

    id: str
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    current: bool


class SecurityInfo(BaseModel):
    """What *Me → Security* shows, e.g. "Password reset by X on <date>" (ACC-10).

    `password_reset_by` is null for a reset link from the command line or a deleted admin.
    """

    password_changed_at: datetime | None
    password_reset_at: datetime | None
    password_reset_by: UserRef | None
