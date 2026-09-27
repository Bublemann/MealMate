"""Sessions: login, refresh with rotation and fork, logout, and the per-request check (§ 5.4)."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode, rate_limited
from app.core.passwords import verify_password
from app.core.ratelimit import LoginThrottle
from app.core.tokens import (
    ACCESS_TOKEN_TTL,
    AccessTokenExpiredError,
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    random_token,
)
from app.domain.accounts import username_norm
from app.domain.sessions import RefreshOutcome, RefreshTokenState, decide_refresh
from app.models import AuthSession, SessionToken, User
from app.repositories import sessions as sessions_repo
from app.repositories import users as users_repo
from app.schemas.auth import LoginResponse
from app.schemas.users import Me
from app.services.context import AuthConfig
from app.services.principal import Principal

USER_AGENT_MAX_LENGTH = 200


@dataclass(frozen=True, repr=False)
class LoginResult:
    """The response body plus the refresh token for the cookie."""

    response: LoginResponse
    refresh_token: str


def _unauthorized(code: ErrorCode) -> ApiError:
    return ApiError(code, status_code=401)


def trim_user_agent(user_agent: str | None) -> str | None:
    return (user_agent or "").strip()[:USER_AGENT_MAX_LENGTH] or None


def _issue_token(session: AsyncSession, config: AuthConfig, session_id: str, now: datetime) -> str:
    token = random_token()
    session.add(
        SessionToken(
            session_id=session_id,
            token_hmac=config.code_hash(token),
            issued_at=now,
            expires_at=now + config.session_idle,
        )
    )
    return token


def _login_response(
    config: AuthConfig, user: User, session_id: str, now: datetime
) -> LoginResponse:
    return LoginResponse(
        access_token=create_access_token(
            config.keys.jwt, user_id=user.id, session_id=session_id, now=now
        ),
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        user=Me.model_validate(user),
    )


async def open_session(
    session: AsyncSession,
    config: AuthConfig,
    user: User,
    *,
    now: datetime,
    user_agent: str | None,
) -> LoginResult:
    """Start a new session for `user` inside the caller's transaction."""
    auth_session = AuthSession(
        user_id=user.id,
        created_at=now,
        last_used_at=now,
        expires_at=now + config.session_idle,
        user_agent=trim_user_agent(user_agent),
    )
    session.add(auth_session)
    await session.flush()
    refresh_token = _issue_token(session, config, auth_session.id, now)
    user.last_seen_at = now
    return LoginResult(_login_response(config, user, auth_session.id, now), refresh_token)


async def login(
    session: AsyncSession,
    config: AuthConfig,
    throttle: LoginThrottle,
    *,
    username: str,
    password: str,
    client_ip: str,
    now: datetime,
    user_agent: str | None,
) -> LoginResult:
    """Check the password (ACC-11: throttled per username and client), then open a session."""
    keys = (f"user:{username_norm(username)}", f"ip:{client_ip}")
    if (retry_after := throttle.retry_after(keys)) is not None:
        raise rate_limited(retry_after)

    async with session.begin():
        user = await users_repo.by_username_norm(session, username_norm(username))
        password_hash = None if user is None else user.password_hash
    if not await verify_password(password, password_hash, rounds=config.bcrypt_rounds):
        throttle.record_failure(keys)
        raise _unauthorized(ErrorCode.INVALID_CREDENTIALS)

    throttle.reset(keys)
    session.expire_all()  # read the user afresh; bcrypt took a while
    async with session.begin():
        user = await users_repo.by_username_norm(session, username_norm(username))
        # Deleted or changed while bcrypt ran: treat like a wrong password.
        if user is None or user.password_hash != password_hash:
            raise _unauthorized(ErrorCode.INVALID_CREDENTIALS)
        if not user.is_active:
            raise ApiError(ErrorCode.ACCOUNT_DEACTIVATED, status_code=403)
        return await open_session(session, config, user, now=now, user_agent=user_agent)


async def refresh(
    session: AsyncSession,
    config: AuthConfig,
    *,
    refresh_token: str | None,
    fork: bool,
    now: datetime,
    user_agent: str | None,
) -> LoginResult:
    """Rotate the refresh token, or fork a new session (see `app.domain.sessions`).

    Reuse of an old token revokes the session; that revocation is committed before the error
    is raised.
    """
    if not refresh_token:
        raise _unauthorized(ErrorCode.SESSION_EXPIRED)

    result: LoginResult | None = None
    async with session.begin():
        found = await sessions_repo.token_by_hmac(session, config.code_hash(refresh_token))
        if found is None:
            outcome = RefreshOutcome.EXPIRED
        else:
            token, auth_session, user = found
            outcome = decide_refresh(
                RefreshTokenState(
                    token_expires_at=token.expires_at,
                    superseded_at=token.superseded_at,
                    forked_at=token.forked_at,
                    session_expires_at=auth_session.expires_at,
                    session_revoked_at=auth_session.revoked_at,
                ),
                now=now,
                fork=fork,
            )
            if not user.is_active and outcome is not RefreshOutcome.EXPIRED:
                outcome = RefreshOutcome.REVOKED
            if outcome in (RefreshOutcome.ROTATE, RefreshOutcome.GRACE):
                if outcome is RefreshOutcome.ROTATE:
                    await sessions_repo.supersede_active_tokens(session, auth_session.id, now)
                auth_session.last_used_at = now
                auth_session.expires_at = now + config.session_idle
                user.last_seen_at = now
                new_token = _issue_token(session, config, auth_session.id, now)
                result = LoginResult(_login_response(config, user, auth_session.id, now), new_token)
            elif outcome is RefreshOutcome.FORK:
                token.forked_at = now
                result = await open_session(session, config, user, now=now, user_agent=user_agent)
            elif outcome is RefreshOutcome.REUSE:
                auth_session.revoked_at = now

    if result is not None:
        return result
    if outcome is RefreshOutcome.FORK_REFUSED:
        raise _unauthorized(ErrorCode.LOGIN_REQUIRED)
    if outcome in (RefreshOutcome.REVOKED, RefreshOutcome.REUSE):
        raise _unauthorized(ErrorCode.SESSION_REVOKED)
    raise _unauthorized(ErrorCode.SESSION_EXPIRED)


async def logout(
    session: AsyncSession, config: AuthConfig, *, refresh_token: str | None, now: datetime
) -> None:
    """Revoke the session the refresh cookie belongs to, if any; never fails."""
    if not refresh_token:
        return
    async with session.begin():
        found = await sessions_repo.token_by_hmac(session, config.code_hash(refresh_token))
        if found is not None and found[1].revoked_at is None:
            found[1].revoked_at = now


async def logout_all(session: AsyncSession, principal: Principal, *, now: datetime) -> None:
    """Revoke every session of the user, the current one included (ACC-09)."""
    async with session.begin():
        await sessions_repo.revoke_for_user(session, principal.user_id, now)


async def authenticate(
    session: AsyncSession, config: AuthConfig, *, access_token: str, now: datetime
) -> Principal:
    """The per-request check: a valid access token whose session is live and whose user is
    active. Session and user come from one indexed lookup; the role from the database."""
    try:
        claims = decode_access_token(config.keys.jwt, access_token, now=now)
    except AccessTokenExpiredError:
        raise _unauthorized(ErrorCode.TOKEN_EXPIRED) from None
    except InvalidAccessTokenError:
        raise _unauthorized(ErrorCode.UNAUTHORIZED) from None

    async with session.begin():
        found = await sessions_repo.with_user(session, claims.session_id)
    if found is None:
        # The session is gone, which only happens when its user was deleted.
        raise _unauthorized(ErrorCode.SESSION_REVOKED)
    auth_session, user = found
    if user.id != claims.user_id:
        raise _unauthorized(ErrorCode.UNAUTHORIZED)
    if auth_session.revoked_at is not None or not user.is_active:
        raise _unauthorized(ErrorCode.SESSION_REVOKED)
    if auth_session.expires_at <= now:
        raise _unauthorized(ErrorCode.SESSION_EXPIRED)
    return Principal(user_id=user.id, session_id=auth_session.id, role=user.role)
