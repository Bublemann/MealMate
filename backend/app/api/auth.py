"""Login, refresh, logout, invites and reset links (plan § 5.4, ACC)."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Response, status
from starlette.responses import Response as PlainResponse

from app.api.deps import (
    AppSettings,
    ClientIp,
    Config,
    CurrentUser,
    Limits,
    Now,
    UserAgent,
    limit_code_requests,
)
from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode
from app.db.session import ReadSession, WriteSession
from app.schemas.auth import (
    CodeCheckRequest,
    CodeInfo,
    JoinRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    ResetRequest,
)
from app.schemas.errors import ERROR_RESPONSES
from app.services import auth, codes
from app.services.auth import LoginResult

REFRESH_COOKIE = "mm_refresh"
REFRESH_COOKIE_PATH = "/api/auth"
CLIENT_HEADER = "X-MealMate-Client"
CLIENT_HEADER_VALUE = "web"

router = APIRouter(prefix="/api/auth", tags=["auth"], responses=ERROR_RESPONSES)

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE)]


def _cookie_max_age(settings: Settings) -> int:
    return settings.session_idle_days * 24 * 60 * 60


def set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    """`HttpOnly; Secure; SameSite=Strict; Path=/api/auth`, kept for the idle limit."""
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=_cookie_max_age(settings),
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _clear_cookie_header(settings: Settings) -> str:
    """The `Set-Cookie` value that removes the refresh cookie, for error responses."""
    response = PlainResponse()
    clear_refresh_cookie(response, settings)
    return response.headers["set-cookie"]


def _logged_in(response: Response, settings: Settings, result: LoginResult) -> LoginResponse:
    set_refresh_cookie(response, settings, result.refresh_token)
    return result.response


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    session: WriteSession,
    settings: AppSettings,
    config: Config,
    limits: Limits,
    client_ip: ClientIp,
    user_agent: UserAgent,
    now: Now,
) -> LoginResponse:
    """Log in with username and password; sets the refresh cookie (throttled, ACC-11)."""
    result = await auth.login(
        session,
        config,
        limits.login,
        username=body.username,
        password=body.password,
        client_ip=client_ip,
        now=now,
        user_agent=user_agent,
    )
    return _logged_in(response, settings, result)


@router.post("/refresh")
async def refresh(
    response: Response,
    session: WriteSession,
    settings: AppSettings,
    config: Config,
    user_agent: UserAgent,
    now: Now,
    body: RefreshRequest | None = None,
    mm_refresh: RefreshCookie = None,
    client: Annotated[str | None, Header(alias=CLIENT_HEADER)] = None,
) -> LoginResponse:
    """A new access token (and rotated cookie) for the refresh cookie.

    Needs the header `X-MealMate-Client: web` (CSRF guard). `{"fork": true}` starts a new,
    independent session instead (first start of the Home Screen app).
    """
    if client != CLIENT_HEADER_VALUE:
        raise ApiError(ErrorCode.CSRF, status_code=403)
    try:
        result = await auth.refresh(
            session,
            config,
            refresh_token=mm_refresh,
            fork=body is not None and body.fork,
            now=now,
            user_agent=user_agent,
        )
    except ApiError as exc:
        if exc.code in {ErrorCode.SESSION_EXPIRED, ErrorCode.SESSION_REVOKED}:
            exc.headers["set-cookie"] = _clear_cookie_header(settings)
        raise
    return _logged_in(response, settings, result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(
    response: Response,
    session: WriteSession,
    settings: AppSettings,
    config: Config,
    now: Now,
    mm_refresh: RefreshCookie = None,
) -> None:
    """Log out this device: revoke the cookie's session and remove the cookie."""
    await auth.logout(session, config, refresh_token=mm_refresh, now=now)
    clear_refresh_cookie(response, settings)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout_all(
    principal: CurrentUser,
    response: Response,
    session: WriteSession,
    settings: AppSettings,
    now: Now,
) -> None:
    """Log out every device of the user, this one included (ACC-09)."""
    await auth.logout_all(session, principal, now=now)
    clear_refresh_cookie(response, settings)


@router.post("/codes/check", dependencies=[Depends(limit_code_requests)])
async def check_code(
    body: CodeCheckRequest, session: ReadSession, config: Config, now: Now
) -> CodeInfo:
    """Whether an invite or reset code can be used; does not consume it (ACC-04)."""
    return await codes.check_code(session, config, code=body.code, now=now)


@router.post(
    "/join", status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit_code_requests)]
)
async def join(
    body: JoinRequest,
    response: Response,
    session: WriteSession,
    settings: AppSettings,
    config: Config,
    user_agent: UserAgent,
    now: Now,
) -> LoginResponse:
    """Register with an invite code and log in (ACC-01, ACC-05, ACC-07)."""
    result = await codes.join(session, config, body, now=now, user_agent=user_agent)
    return _logged_in(response, settings, result)


@router.post("/reset", dependencies=[Depends(limit_code_requests)])
async def reset_password(
    body: ResetRequest,
    response: Response,
    session: WriteSession,
    settings: AppSettings,
    config: Config,
    user_agent: UserAgent,
    now: Now,
) -> LoginResponse:
    """Set a new password with a reset code; ends all other sessions and logs in (ACC-10)."""
    result = await codes.reset_password(
        session, config, code=body.code, password=body.password, now=now, user_agent=user_agent
    )
    return _logged_in(response, settings, result)
