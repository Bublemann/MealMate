"""System info and the manual backup request on the admin page (ADM-01, OPS-08, plan § 11).

The host scripts (`deploy/pi/bin/`) run as root and hand their results to the app as small
JSON files in their own `state/status/`, which the container sees read-only at
`MEALMATE_STATUS_DIR` (default `/status`). Each is written atomically (a temporary file, then
`mv -fT`), mode 0644, UTF-8, at most 4 KB:

- `backup.json`, after every `backup.sh` run (`ok` false when it failed)::

    {"finished_at": "2026-09-27T12:15:04Z", "label": "regular" | "pre-update" | "manual",
     "ok": true, "snapshot": "20260927T121500Z" | null, "size_bytes": 12345 | null,
     "message": "short status line" | null}

- `disk.json`, hourly from `disk-check.sh`::

    {"checked_at": "2026-09-27T12:00:02Z", "free_bytes": 1234, "total_bytes": 5678,
     "free_percent": 21.7}

The app reads them tolerantly: a missing, unreadable, oversized or invalid file (or one that is
not a regular file) shows as "no status" (null), unknown keys are ignored, and an invalid
optional value becomes null. The message is shown as plain text, never as HTML, cut to one short
line.

In the other direction, "Back up now" creates the empty file `<data dir>/status/backup-request`.
The host's `mealmate-backup.path` unit notices it and runs `backup.sh --label manual`, which
deletes it first. The file is created with `O_CREAT | O_EXCL | O_NOFOLLOW` inside a directory
opened with `O_NOFOLLOW`, so nothing is ever written through a symlink; a request that is
already waiting (or any file at that path) leaves the request as it is.
"""

import json
import logging
import os
import stat
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import anyio
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    ValidatorFunctionWrapHandler,
    field_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, source_url
from app.core.errors import ApiError, ErrorCode
from app.schemas.admin import AdminAction, BackupStatus, DiskStatus, SystemInfo
from app.services import events
from app.services.principal import Principal

logger = logging.getLogger(__name__)

BACKUP_STATUS_FILENAME = "backup.json"
DISK_STATUS_FILENAME = "disk.json"
BACKUP_REQUEST_FILENAME = "backup-request"
MAX_STATUS_FILE_BYTES = 4096
MESSAGE_MAX_LENGTH = 200


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _one_line(text: str) -> str | None:
    """Control characters and runs of whitespace become single spaces; at most 200 chars."""
    printable = "".join(char if char.isprintable() else " " for char in text)
    return " ".join(printable.split())[:MESSAGE_MAX_LENGTH] or None


def _null_if_invalid(value: object, handler: ValidatorFunctionWrapHandler) -> object:
    try:
        return handler(value)
    except ValidationError:
        return None


class _BackupFile(BackupStatus):
    """`backup.json`; an invalid optional value becomes null instead of failing the file."""

    size_bytes: int | None = Field(default=None, ge=0)
    message: str | None = None

    @field_validator("finished_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("size_bytes", mode="wrap")
    @classmethod
    def _tolerate_size(cls, value: object, handler: ValidatorFunctionWrapHandler) -> object:
        return _null_if_invalid(value, handler)

    @field_validator("message", mode="wrap")
    @classmethod
    def _tolerate_message(cls, value: object, handler: ValidatorFunctionWrapHandler) -> object:
        message = _null_if_invalid(value, handler)
        return _one_line(message) if isinstance(message, str) else None


class _DiskFile(DiskStatus):
    @field_validator("checked_at")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        return _utc(value)


def _read_status_file(path: Path) -> bytes | None:
    """The file's bytes if it is a regular file (not a symlink) of at most 4 KB, else None."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("status file %s cannot be opened: %s", path.name, exc.strerror)
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            logger.warning("status file %s is not a regular file", path.name)
            return None
        data = os.read(fd, MAX_STATUS_FILE_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_STATUS_FILE_BYTES:
        logger.warning("status file %s is larger than %d bytes", path.name, MAX_STATUS_FILE_BYTES)
        return None
    return data


def _parse[T: BaseModel](path: Path, model: type[T]) -> T | None:
    data = _read_status_file(path)
    if data is None:
        return None
    try:
        return model.model_validate(json.loads(data.decode("utf-8")))
    except UnicodeDecodeError, json.JSONDecodeError, ValidationError:
        logger.warning("status file %s is invalid", path.name)
        return None


def _host_status(status_dir: Path) -> tuple[BackupStatus | None, DiskStatus | None]:
    return (
        _parse(status_dir / BACKUP_STATUS_FILENAME, _BackupFile),
        _parse(status_dir / DISK_STATUS_FILENAME, _DiskFile),
    )


async def system_info(settings: Settings) -> SystemInfo:
    """The running version and the host's last backup and disk check (ADM-01)."""
    backup, disk = await anyio.to_thread.run_sync(partial(_host_status, settings.status_dir))
    return SystemInfo(
        version=settings.version,
        commit=settings.commit,
        source_url=source_url(settings.commit),
        image_digest=settings.image_digest,
        backup=backup,
        disk=disk,
    )


def create_backup_request(status_dir: Path) -> bool:
    """Create the empty request file without following symlinks; returns False if something
    already exists at that path (a request is waiting)."""
    status_dir.mkdir(exist_ok=True)
    dir_fd = os.open(status_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        fd = os.open(
            BACKUP_REQUEST_FILENAME,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=dir_fd,
        )
    except FileExistsError:
        return False
    finally:
        os.close(dir_fd)
    os.close(fd)
    return True


async def request_backup(
    session: AsyncSession, settings: Settings, actor: Principal, *, now: datetime
) -> None:
    """Ask the host for a backup now (OPS-08) and log who did. 503 if the request file can't
    be created (e.g. the data directory is not writable)."""
    async with session.begin():
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.SYSTEM_BACKUP_REQUEST,
            target_user_id=None,
            now=now,
        )
        try:
            created = await anyio.to_thread.run_sync(
                partial(create_backup_request, settings.data_status_dir)
            )
        except OSError as exc:
            logger.warning("backup request cannot be created: %s", exc.strerror)
            raise ApiError(ErrorCode.SERVICE_UNAVAILABLE, status_code=503) from None
    logger.info("backup requested" if created else "backup request already waiting")
