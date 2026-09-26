"""Cookie carry-over test for the M1 platform spike (plan § 7).

Registered only with `MEALMATE_DIAGNOSTICS_ENABLED=true`, and removed in M9. The cookie has
the same attributes as the refresh cookie, and lives under `/api/auth` for the same path.
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, Response, status

from app.api.deps import AppSettings
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.system import DiagCookieCheck

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
