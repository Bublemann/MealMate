"""Login, refresh, invite and reset requests (plan § 5.4)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.domain.accounts import USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH, USERNAME_PATTERN
from app.schemas.users import DisplayNameInput, Language, Me, PasswordInput

CodeInput = Annotated[str, StringConstraints(min_length=1, max_length=100)]
UsernameInput = Annotated[
    str,
    StringConstraints(
        min_length=USERNAME_MIN_LENGTH, max_length=USERNAME_MAX_LENGTH, pattern=USERNAME_PATTERN
    ),
]


class LoginRequest(BaseModel):
    username: Annotated[str, StringConstraints(max_length=100)]
    password: PasswordInput


class RefreshRequest(BaseModel):
    """`fork` asks for a new, independent session (first start of the Home Screen app)."""

    fork: bool = False


class LoginResponse(BaseModel):
    """`access_token` goes into `Authorization: Bearer`; it expires after `expires_in` s."""

    access_token: str
    expires_in: int
    user: Me


class CodeCheckRequest(BaseModel):
    code: CodeInput


class CodeInfo(BaseModel):
    """A usable code. `username` is set for reset codes only (the account being reset)."""

    kind: Literal["invite", "reset"]
    expires_at: datetime
    username: str | None


class JoinRequest(BaseModel):
    """Registration with an invite code (ACC-05)."""

    code: CodeInput
    username: UsernameInput
    display_name: DisplayNameInput
    password: PasswordInput
    language: Language


class ResetRequest(BaseModel):
    code: CodeInput
    password: PasswordInput
