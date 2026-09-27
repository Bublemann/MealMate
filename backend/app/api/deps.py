"""Shared FastAPI dependencies."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.errors import ApiError, ErrorCode, rate_limited
from app.core.ratelimit import RateLimits
from app.db.session import Database, ReadSession, get_database
from app.media.store import MediaStore
from app.services import access, auth
from app.services.context import AuthConfig
from app.services.list_cache import ListCache
from app.services.off_refresh import OffRefresher
from app.services.principal import Principal

UNKNOWN_CLIENT = "unknown"


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_auth_config(request: Request) -> AuthConfig:
    config: AuthConfig = request.app.state.auth_config
    return config


def get_rate_limits(request: Request) -> RateLimits:
    limits: RateLimits = request.app.state.rate_limits
    return limits


def get_media(request: Request) -> MediaStore:
    media: MediaStore = request.app.state.media
    return media


def get_list_cache(request: Request) -> ListCache:
    cache: ListCache = request.app.state.list_cache
    return cache


def get_off_refresher(request: Request) -> OffRefresher:
    refresher: OffRefresher = request.app.state.off_refresh
    return refresher


def get_now(request: Request) -> datetime:
    """The current time from the app's clock (`app.state.clock`), which tests can move."""
    clock: Callable[[], datetime] = request.app.state.clock
    return clock()


def get_client_ip(request: Request) -> str:
    """The client address. uvicorn takes it from `X-Forwarded-For` only when the request comes
    from 127.0.0.1, where `tailscale serve` connects from (plan § 2, SEC-05)."""
    return request.client.host if request.client else UNKNOWN_CLIENT


def get_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


AppSettings = Annotated[Settings, Depends(get_app_settings)]
Config = Annotated[AuthConfig, Depends(get_auth_config)]
Limits = Annotated[RateLimits, Depends(get_rate_limits)]
Media = Annotated[MediaStore, Depends(get_media)]
Db = Annotated[Database, Depends(get_database)]
ListResponses = Annotated[ListCache, Depends(get_list_cache)]
OffRefresh = Annotated[OffRefresher, Depends(get_off_refresher)]
Now = Annotated[datetime, Depends(get_now)]
ClientIp = Annotated[str, Depends(get_client_ip)]
UserAgent = Annotated[str | None, Depends(get_user_agent)]

_bearer = HTTPBearer(
    auto_error=False, description="The access token from login, refresh, join or reset."
)


async def current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: ReadSession,
    config: Config,
    now: Now,
) -> Principal:
    """The authenticated user (401 without a valid bearer token and a live session)."""
    if credentials is None:
        raise ApiError(ErrorCode.UNAUTHORIZED, status_code=401)
    return await auth.authenticate(session, config, access_token=credentials.credentials, now=now)


CurrentUser = Annotated[Principal, Depends(current_principal)]


async def admin_principal(principal: CurrentUser) -> Principal:
    """An authenticated, active admin (403 `common.forbidden` for everyone else)."""
    access.require_admin(principal)
    return principal


CurrentAdmin = Annotated[Principal, Depends(admin_principal)]


async def limit_code_requests(limits: Limits, client_ip: ClientIp) -> None:
    """Join, reset and code checks: at most 10 requests per minute per client (SEC-05)."""
    if (retry_after := limits.codes.hit(client_ip)) is not None:
        raise rate_limited(retry_after)


async def limit_uploads(limits: Limits, principal: CurrentUser) -> None:
    """Photo uploads: at most 20 per 10 minutes per user (SEC-07, PERF-05)."""
    if (retry_after := limits.uploads.hit(principal.user_id)) is not None:
        raise rate_limited(retry_after)
