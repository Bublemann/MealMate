"""Admin section: users, invites, reset links, the activity log and system info (ADM-01)."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints, field_validator

from app.schemas.users import Role, UserRef

InviteStatus = Literal["open", "used", "expired", "revoked"]
BackupLabel = Literal["regular", "pre-update", "manual"]
# A plain alias so the OpenAPI schema inlines the union.
AdminEventDetail = str | int | bool | None


class AdminAction(StrEnum):
    """What an admin (or the command line, with no actor) did."""

    INVITE_CREATE = "invite.create"
    INVITE_REVOKE = "invite.revoke"
    USER_RESET_LINK = "user.reset_link"
    USER_ROLE_CHANGE = "user.role_change"
    USER_DEACTIVATE = "user.deactivate"
    USER_REACTIVATE = "user.reactivate"
    USER_DELETE = "user.delete"
    CATEGORY_CREATE = "category.create"
    CATEGORY_RENAME = "category.rename"
    CATEGORY_REORDER = "category.reorder"
    INGREDIENT_MERGE = "ingredient.merge"
    INGREDIENT_DELETE = "ingredient.delete"
    SYSTEM_BACKUP_REQUEST = "system.backup_request"


class AdminUser(BaseModel):
    id: str
    username: str
    display_name: str
    role: Role
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None


class AdminUserUpdate(BaseModel):
    """Only the fields that are sent change."""

    role: Role | None = None
    is_active: bool | None = None


class LinkCreated(BaseModel):
    """A reset link; the code is in the fragment (`/reset#<code>`)."""

    url: str
    expires_at: datetime


class Invite(BaseModel):
    id: str
    status: InviteStatus
    created_at: datetime
    expires_at: datetime
    created_by: UserRef | None
    used_by: UserRef | None
    tailscale_share_url: str | None


class InviteCreate(BaseModel):
    """`tailscale_share_url`: the optional share link for step 1 of the invite message."""

    tailscale_share_url: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None
    ) = None

    @field_validator("tailscale_share_url")
    @classmethod
    def _check_https_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError("must be an https URL")
        return value


class InviteCreated(BaseModel):
    """The new invite and its link (`/join#<code>`); the code is shown only this once."""

    invite: Invite
    url: str


class AdminEvent(BaseModel):
    """`actor` is null for the command line or a deleted admin, `target` for a deleted user."""

    id: str
    actor: UserRef | None
    action: AdminAction
    target: UserRef | None
    details: dict[str, AdminEventDetail]
    created_at: datetime


class BackupStatus(BaseModel):
    """The host's last backup run (`backup.json`); `ok` false means it failed (OPS-01)."""

    finished_at: AwareDatetime
    label: BackupLabel
    ok: bool
    size_bytes: int | None = Field(ge=0)
    message: str | None


class DiskStatus(BaseModel):
    """Free space on the Pi's root file system when the host last checked (`disk.json`)."""

    checked_at: AwareDatetime
    free_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    free_percent: float = Field(ge=0, le=100)


class SystemInfo(BaseModel):
    """What is running and how the host is doing (ADM-01). `backup` and `disk` are null
    while the host has not written its status files (or they can't be read)."""

    version: str
    commit: str
    source_url: str
    image_digest: str | None
    backup: BackupStatus | None
    disk: DiskStatus | None
