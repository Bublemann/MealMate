"""Diagnostics for the M1 platform spike (plan § 7, § 12), used by the frontend's `/diag` screen.

Registered only with `MEALMATE_DIAGNOSTICS_ENABLED=true`, and removed in M9. The cookie
carry-over test (O-10) uses a cookie with the same attributes as the refresh cookie, under
`/api/auth` for the same path. The request echo (O-3) shows what the app sees of the request.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response, status

from app.api.deps import AppSettings, ClientIp
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.system import DiagCookieCheck, DiagRequestInfo

DIAG_COOKIE = "mm_diag"
DIAG_COOKIE_PATH = "/api/auth"
DIAG_COOKIE_MAX_AGE = 90 * 24 * 60 * 60

router = APIRouter(prefix="/api/auth/diag", tags=["diagnostics"], responses=ERROR_RESPONSES)


@router.post("/set", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def set_diag_cookie(response: Response, settings: AppSettings) -> None:
    """Sets the diagnostics cookie."""
    response.set_cookie(
        DIAG_COOKIE,
        "1",
        max_age=DIAG_COOKIE_MAX_AGE,
        path=DIAG_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.post("/check")
async def check_diag_cookie(
    mm_diag: Annotated[str | None, Cookie()] = None,
) -> DiagCookieCheck:
    """Reports whether the browser sent the diagnostics cookie."""
    return DiagCookieCheck(present=mm_diag == "1")


@router.get("/request")
async def get_diag_request(request: Request, client_ip: ClientIp) -> DiagRequestInfo:
    """The request as the app sees it, after uvicorn applied the proxy headers (O-3).

    Behind `tailscale serve`, `client_host` should be the phone's tailnet IP and `scheme` should
    be `https`, because uvicorn trusts `X-Forwarded-*` from 127.0.0.1. `client_host` is the same
    value that login throttling uses (`ClientIp`). The raw forwarded headers are shown too, so a
    mismatch tells whether the proxy did not send them or uvicorn ignored them.
    """
    headers = request.headers
    return DiagRequestInfo(
        client_host=client_ip,
        scheme=request.url.scheme,
        host_header=headers.get("host"),
        x_forwarded_for=headers.get("x-forwarded-for"),
        x_forwarded_proto=headers.get("x-forwarded-proto"),
    )
