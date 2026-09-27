"""Health and version (plan § 7, LIC-02)."""

import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AppSettings
from app.core.config import REPO_URL
from app.core.errors import ApiError, ErrorCode
from app.db.session import ReadSession
from app.schemas.errors import ERROR_RESPONSES, ErrorResponse
from app.schemas.system import HealthStatus, VersionInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"], responses=ERROR_RESPONSES)

_COMMIT_SHA = re.compile(r"[0-9a-f]{7,40}")


def source_url(commit: str) -> str:
    """The source of the running build: the exact commit if known, else the repository."""
    return f"{REPO_URL}/tree/{commit}" if _COMMIT_SHA.fullmatch(commit) else REPO_URL


async def _database_ok(session: AsyncSession) -> bool:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.warning("health check: database unavailable", exc_info=True)
        return False
    return True


def _data_dir_writable(data_dir: Path) -> bool:
    if os.access(data_dir, os.W_OK):
        return True
    logger.warning("health check: data directory not writable")
    return False


@router.get(
    "/health",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "The database or the data directory is unavailable",
        }
    },
)
async def get_health(session: ReadSession, settings: AppSettings) -> HealthStatus:
    """Checks that the database answers and the data directory is writable."""
    if not (await _database_ok(session) and _data_dir_writable(settings.data_dir)):
        raise ApiError(
            ErrorCode.SERVICE_UNAVAILABLE, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    return HealthStatus(status="ok")


@router.get("/version")
async def get_version(settings: AppSettings) -> VersionInfo:
    """The running version and a link to its source code."""
    return VersionInfo(
        version=settings.version, commit=settings.commit, source_url=source_url(settings.commit)
    )
