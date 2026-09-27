"""Invites and reset links: create, check, consume, revoke (ACC-01..04, ACC-07, ACC-10).

Codes travel in the URL fragment (`/join#<code>`, `/reset#<code>`), are stored as HMACs, and are
consumed only by `join` or `reset_password` (ACC-04). Checking a code does not consume it.
"""

from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode, not_found, validation_error
from app.core.passwords import hash_password
from app.core.tokens import random_token
from app.models import OneTimeCode, User
from app.repositories import codes as codes_repo
from app.repositories import sessions as sessions_repo
from app.repositories import users as users_repo
from app.schemas.admin import AdminAction, Invite, InviteCreated, InviteStatus, LinkCreated
from app.schemas.auth import CodeInfo, JoinRequest
from app.schemas.users import UserRef
from app.services import accounts, events
from app.services.auth import LoginResult, open_session
from app.services.context import AuthConfig
from app.services.users import user_refs

JOIN_PATH = "/join"
RESET_PATH = "/reset"


def _code_invalid() -> ApiError:
    return ApiError(ErrorCode.CODE_INVALID, status_code=404)


def _deactivated() -> ApiError:
    return ApiError(ErrorCode.ACCOUNT_DEACTIVATED, status_code=403)


def require_public_url(config: AuthConfig) -> str:
    """Links need `MEALMATE_PUBLIC_URL`; without it nothing is created (503)."""
    if config.public_url is None:
        raise ApiError(ErrorCode.ADMIN_PUBLIC_URL_MISSING, status_code=503)
    return config.public_url


def invite_status(code: OneTimeCode, now: datetime) -> InviteStatus:
    if code.used_at is not None:
        return "used"
    if code.revoked_at is not None:
        return "revoked"
    if code.expires_at <= now:
        return "expired"
    return "open"


def _invite(code: OneTimeCode, refs: dict[str, UserRef], now: datetime) -> Invite:
    return Invite(
        id=code.id,
        status=invite_status(code, now),
        created_at=code.created_at,
        expires_at=code.expires_at,
        created_by=refs.get(code.created_by) if code.created_by else None,
        used_by=refs.get(code.used_by) if code.used_by else None,
        tailscale_share_url=code.tailscale_share_url,
    )


async def _open_code(
    session: AsyncSession, config: AuthConfig, code: str, now: datetime
) -> OneTimeCode | None:
    """The code if it can still be used: known, not used, not revoked, not expired."""
    found = await codes_repo.by_hmac(session, config.code_hash(code))
    if found is None or invite_status(found, now) != "open":
        return None
    return found


async def _reset_target(
    session: AsyncSession, config: AuthConfig, code: str, now: datetime
) -> tuple[OneTimeCode, User]:
    """The open reset code and the active user it resets."""
    reset = await _open_code(session, config, code, now)
    user = None
    if reset is not None and reset.kind == "reset" and reset.target_user_id is not None:
        user = await users_repo.get(session, reset.target_user_id)
    if reset is None or user is None:
        raise _code_invalid()
    if not user.is_active:
        raise _deactivated()
    return reset, user


async def create_invite(
    session: AsyncSession,
    config: AuthConfig,
    *,
    actor_id: str | None,
    tailscale_share_url: str | None,
    now: datetime,
) -> InviteCreated:
    async with session.begin():
        return await insert_invite(
            session, config, actor_id=actor_id, tailscale_share_url=tailscale_share_url, now=now
        )


async def insert_invite(
    session: AsyncSession,
    config: AuthConfig,
    *,
    actor_id: str | None,
    tailscale_share_url: str | None,
    now: datetime,
) -> InviteCreated:
    """`create_invite` inside the caller's transaction (the demo data adds one)."""
    public_url = require_public_url(config)
    code = random_token()
    invite = OneTimeCode(
        kind="invite",
        code_hmac=config.code_hash(code),
        created_by=actor_id,
        expires_at=now + config.invite_ttl,
        tailscale_share_url=tailscale_share_url,
        created_at=now,
        updated_at=now,
    )
    session.add(invite)
    await session.flush()
    events.record(
        session,
        actor_id=actor_id,
        action=AdminAction.INVITE_CREATE,
        target_user_id=None,
        now=now,
        details={"invite_id": invite.id},
    )
    refs = await user_refs(session, [actor_id])
    return InviteCreated(invite=_invite(invite, refs, now), url=f"{public_url}{JOIN_PATH}#{code}")


async def list_invites(session: AsyncSession, *, now: datetime) -> list[Invite]:
    """All invites, newest first, with their status (ADM-01)."""
    async with session.begin():
        invites = await codes_repo.invites_newest_first(session)
        refs = await user_refs(
            session, [user_id for code in invites for user_id in (code.created_by, code.used_by)]
        )
    return [_invite(code, refs, now) for code in invites]


async def revoke_invite(
    session: AsyncSession, *, actor_id: str, invite_id: str, now: datetime
) -> None:
    """Revoke an open invite. Revoking a used, expired or revoked one changes nothing."""
    async with session.begin():
        invite = await codes_repo.get(session, invite_id)
        if invite is None or invite.kind != "invite":
            raise not_found()
        if invite_status(invite, now) == "open":
            invite.revoked_at = now
            events.record(
                session,
                actor_id=actor_id,
                action=AdminAction.INVITE_REVOKE,
                target_user_id=None,
                now=now,
                details={"invite_id": invite.id},
            )


async def create_reset_link(
    session: AsyncSession,
    config: AuthConfig,
    *,
    actor_id: str | None,
    user_id: str,
    now: datetime,
    reactivate: bool = False,
) -> LinkCreated:
    """A new reset link for the user; older open ones are revoked (ACC-10).

    `reactivate` (the `reset-link` command, ACC-12) also reactivates the account.
    """
    public_url = require_public_url(config)
    code = random_token()
    async with session.begin():
        user = await users_repo.get(session, user_id)
        if user is None:
            raise not_found()
        await codes_repo.revoke_open_resets(session, user.id, now)
        reset = OneTimeCode(
            kind="reset",
            code_hmac=config.code_hash(code),
            created_by=actor_id,
            target_user_id=user.id,
            expires_at=now + config.reset_ttl,
            created_at=now,
            updated_at=now,
        )
        session.add(reset)
        details = {} if actor_id is not None else {"source": "cli"}
        events.record(
            session,
            actor_id=actor_id,
            action=AdminAction.USER_RESET_LINK,
            target_user_id=user.id,
            now=now,
            details=details,
        )
        if reactivate and not user.is_active:
            user.is_active = True
            events.record(
                session,
                actor_id=actor_id,
                action=AdminAction.USER_REACTIVATE,
                target_user_id=user.id,
                now=now,
                details=details,
            )
    return LinkCreated(url=f"{public_url}{RESET_PATH}#{code}", expires_at=reset.expires_at)


async def check_code(
    session: AsyncSession, config: AuthConfig, *, code: str, now: datetime
) -> CodeInfo:
    """What a code is for, without consuming it; 404 `auth.code_invalid` if it is unusable."""
    async with session.begin():
        found = await _open_code(session, config, code, now)
        if found is None:
            raise _code_invalid()
        username = None
        if found.kind == "reset" and found.target_user_id is not None:
            target = await users_repo.get(session, found.target_user_id)
            username = None if target is None else target.username
    kind: Literal["invite", "reset"] = "reset" if found.kind == "reset" else "invite"
    return CodeInfo(kind=kind, expires_at=found.expires_at, username=username)


async def join(
    session: AsyncSession,
    config: AuthConfig,
    request: JoinRequest,
    *,
    now: datetime,
    user_agent: str | None,
) -> LoginResult:
    """Register with an invite and log in at once (ACC-01, ACC-05, ACC-07)."""
    accounts.check_new_account(request.username, request.display_name, request.password)
    password_hash = await hash_password(request.password, rounds=config.bcrypt_rounds)
    async with session.begin():
        invite = await _open_code(session, config, request.code, now)
        if invite is None or invite.kind != "invite":
            raise _code_invalid()
        user = await accounts.insert_user(
            session,
            username=request.username,
            display_name=request.display_name,
            password_hash=password_hash,
            role="user",
            language=request.language,
            now=now,
        )
        invite.used_at = now
        invite.used_by = user.id
        return await open_session(session, config, user, now=now, user_agent=user_agent)


async def reset_password(
    session: AsyncSession,
    config: AuthConfig,
    *,
    code: str,
    password: str,
    now: datetime,
    user_agent: str | None,
) -> LoginResult:
    """Set a new password with a reset link, end every other session of the user, record who
    reset it (shown in *Me → Security*), and log in (ACC-07, ACC-10)."""
    async with session.begin():
        _, user = await _reset_target(session, config, code, now)
        username = user.username
    if problems := accounts.check_password(password, username=username, loc=("body", "password")):
        raise validation_error(problems)
    password_hash = await hash_password(password, rounds=config.bcrypt_rounds)

    session.expire_all()
    async with session.begin():
        reset, user = await _reset_target(session, config, code, now)
        user.password_hash = password_hash
        user.password_changed_at = now
        user.password_reset_at = now
        user.password_reset_by = reset.created_by
        reset.used_at = now
        reset.used_by = user.id
        await sessions_repo.revoke_for_user(session, user.id, now)
        return await open_session(session, config, user, now=now, user_agent=user_agent)
