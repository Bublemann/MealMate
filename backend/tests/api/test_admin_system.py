"""Admin system info and "Back up now" (ADM-01, OPS-08, SEC-09, plan § 11)."""

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import REPO_URL
from app.models import AdminEvent
from app.services import system
from tests.accounts import Account, FakeClock, error, make_user, scalars

SHA = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "ab" * 32
BACKUP = {
    "finished_at": "2026-09-27T12:15:04Z",
    "label": "regular",
    "ok": True,
    "snapshot": "20260927T121500Z",
    "size_bytes": 12345,
    "message": "backup 20260927T121500Z done",
}
DISK = {
    "checked_at": "2026-09-27T12:00:02Z",
    "free_bytes": 20_000_000_000,
    "total_bytes": 60_000_000_000,
    "free_percent": 33.3,
}


@pytest.fixture
def status_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "status"
    directory.mkdir()
    return directory


@pytest.fixture
def make_settings(make_settings: Any, status_dir: Path) -> Any:
    def make(**overrides: Any) -> Any:
        return make_settings(**({"status_dir": status_dir} | overrides))

    return make


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin", display_name="Admin")


def write_status(status_dir: Path, name: str, content: object) -> Path:
    path = status_dir / name
    path.write_text(content if isinstance(content, str) else json.dumps(content), "utf-8")
    return path


async def system_info(api: AsyncClient, admin: Account) -> Any:
    response = await api.get("/api/admin/system", headers=admin.headers)
    assert response.status_code == 200, response.text
    return response.json()


async def request_backup(api: AsyncClient, admin: Account) -> Any:
    return await api.post("/api/admin/backup", headers=admin.headers)


# --- system info -------------------------------------------------------------------------------


async def test_system_info_without_status_files(api: AsyncClient, admin: Account) -> None:
    assert await system_info(api, admin) == {
        "version": "0.0.0-dev",
        "commit": "unknown",
        "source_url": REPO_URL,
        "image_digest": None,
        "backup": None,
        "disk": None,
    }


async def test_system_info_without_status_dir(
    app: FastAPI, api: AsyncClient, admin: Account, tmp_path: Path
) -> None:
    app.state.settings = app.state.settings.model_copy(update={"status_dir": tmp_path / "none"})
    info = await system_info(api, admin)
    assert (info["backup"], info["disk"]) == (None, None)


async def test_system_info_reads_the_status_files(
    app: FastAPI, api: AsyncClient, admin: Account, status_dir: Path
) -> None:
    app.state.settings = app.state.settings.model_copy(
        update={"version": "2.0.0-pre.3", "commit": SHA, "image_digest": DIGEST}
    )
    write_status(status_dir, "backup.json", BACKUP | {"extra": "ignored"})
    write_status(status_dir, "disk.json", DISK)

    assert await system_info(api, admin) == {
        "version": "2.0.0-pre.3",
        "commit": SHA,
        "source_url": f"{REPO_URL}/tree/{SHA}",
        "image_digest": DIGEST,
        "backup": {
            "finished_at": "2026-09-27T12:15:04Z",
            "label": "regular",
            "ok": True,
            "size_bytes": 12345,
            "message": "backup 20260927T121500Z done",
        },
        "disk": DISK,
    }


async def test_a_failed_backup_in_another_time_zone(
    api: AsyncClient, admin: Account, status_dir: Path
) -> None:
    write_status(
        status_dir,
        "backup.json",
        {
            "finished_at": "2026-09-27T14:15:04+02:00",
            "label": "manual",
            "ok": False,
            "snapshot": None,
            "size_bytes": None,
            "message": "rsync failed",
        },
    )
    write_status(status_dir, "disk.json", DISK | {"checked_at": "2026-09-27T13:00:02+01:00"})

    info = await system_info(api, admin)

    assert info["backup"] == {
        "finished_at": "2026-09-27T12:15:04Z",
        "label": "manual",
        "ok": False,
        "size_bytes": None,
        "message": "rsync failed",
    }
    assert info["disk"]["checked_at"] == "2026-09-27T12:00:02Z"


@pytest.mark.parametrize(
    ("optional", "expected"),
    [
        ({}, {"size_bytes": None, "message": None}),
        ({"size_bytes": -1, "message": 42}, {"size_bytes": None, "message": None}),
        ({"size_bytes": "a lot", "message": " \n\t "}, {"size_bytes": None, "message": None}),
        (
            {"size_bytes": 0, "message": "<b>one</b>\nline\x1b[31m\ttwo  "},
            {"size_bytes": 0, "message": "<b>one</b> line [31m two"},
        ),
        ({"message": "x" * 300}, {"size_bytes": None, "message": "x" * 200}),
    ],
)
async def test_invalid_optional_values_become_null(
    api: AsyncClient,
    admin: Account,
    status_dir: Path,
    optional: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    required = {key: BACKUP[key] for key in ("finished_at", "label", "ok")}
    write_status(status_dir, "backup.json", required | optional)
    assert (await system_info(api, admin))["backup"] == required | expected


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[1, 2]",
        json.dumps(BACKUP)[:-1],
        json.dumps(BACKUP | {"label": "weekly"}),
        json.dumps(BACKUP | {"ok": "maybe"}),
        json.dumps({key: value for key, value in BACKUP.items() if key != "finished_at"}),
        json.dumps(BACKUP | {"finished_at": "2026-09-27T12:15:04"}),  # no time zone
        json.dumps(BACKUP | {"message": "x" * 5000}),  # larger than 4 KB
    ],
)
async def test_an_invalid_backup_file_is_no_status(
    api: AsyncClient,
    admin: Account,
    status_dir: Path,
    content: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    write_status(status_dir, "backup.json", content)
    write_status(status_dir, "disk.json", DISK)
    with caplog.at_level(logging.WARNING, logger="app.services.system"):
        info = await system_info(api, admin)
    assert info["backup"] is None
    assert info["disk"] == DISK
    assert "status file backup.json" in caplog.text


async def test_status_files_that_are_not_utf8_or_out_of_range(
    api: AsyncClient, admin: Account, status_dir: Path
) -> None:
    (status_dir / "backup.json").write_bytes(b'{"label": "\xff"}')
    write_status(status_dir, "disk.json", DISK | {"free_percent": 150})
    info = await system_info(api, admin)
    assert (info["backup"], info["disk"]) == (None, None)


async def test_only_regular_files_are_read(
    api: AsyncClient, admin: Account, status_dir: Path, tmp_path: Path
) -> None:
    elsewhere = write_status(tmp_path, "elsewhere.json", BACKUP)
    (status_dir / "backup.json").symlink_to(elsewhere)
    os.mkfifo(status_dir / "disk.json")  # would block a plain read without a writer
    info = await system_info(api, admin)
    assert (info["backup"], info["disk"]) == (None, None)
    (status_dir / "disk.json").unlink()
    (status_dir / "disk.json").mkdir()
    assert (await system_info(api, admin))["disk"] is None


# --- back up now -------------------------------------------------------------------------------


async def test_backup_request_creates_the_request_file(
    app: FastAPI, api: AsyncClient, admin: Account, data_dir: Path, clock: FakeClock
) -> None:
    request_file = data_dir / "status" / "backup-request"
    assert not request_file.parent.exists()

    response = await request_backup(api, admin)

    assert response.status_code == 202
    assert response.content == b""
    assert request_file.is_file()
    assert request_file.read_bytes() == b""
    assert stat.S_IMODE(request_file.stat().st_mode) & 0o077 == 0
    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert [(event["action"], event["actor"]["id"], event["target"]) for event in events] == [
        ("system.backup_request", admin.id, None)
    ]
    assert events[0]["details"] == {}


async def test_backup_requests_are_limited_to_one_a_minute(
    app: FastAPI, api: AsyncClient, admin: Account, data_dir: Path, clock: FakeClock
) -> None:
    other = await make_user(app, api, "root", role="admin")
    assert (await request_backup(api, admin)).status_code == 202
    clock.advance(seconds=30)

    # For the whole instance, not per admin.
    limited = await request_backup(api, other)

    assert limited.status_code == 429
    assert error(limited) == "common.rate_limited"
    assert limited.headers["Retry-After"] == "30"
    assert len(await scalars(app, select(AdminEvent.id))) == 1

    # A request that is still waiting stays as it is.
    (data_dir / "status" / "backup-request").write_text("waiting")
    clock.advance(seconds=31)
    assert (await request_backup(api, other)).status_code == 202
    assert (data_dir / "status" / "backup-request").read_text() == "waiting"
    assert len(await scalars(app, select(AdminEvent.id))) == 2


async def test_backup_request_never_follows_a_symlink(
    app: FastAPI, api: AsyncClient, admin: Account, data_dir: Path, tmp_path: Path
) -> None:
    (data_dir / "status").mkdir()
    target = tmp_path / "target"
    (data_dir / "status" / "backup-request").symlink_to(target)

    assert (await request_backup(api, admin)).status_code == 202

    assert not target.exists()
    assert (data_dir / "status" / "backup-request").is_symlink()


async def test_backup_request_refuses_a_symlinked_status_dir(
    app: FastAPI,
    api: AsyncClient,
    admin: Account,
    data_dir: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (data_dir / "status").symlink_to(elsewhere)

    with caplog.at_level(logging.WARNING, logger="app.services.system"):
        response = await request_backup(api, admin)

    assert response.status_code == 503
    assert error(response) == "common.service_unavailable"
    assert list(elsewhere.iterdir()) == []
    assert await scalars(app, select(AdminEvent.id)) == []
    assert "backup request cannot be created" in caplog.text


def test_create_backup_request_reports_a_waiting_request(tmp_path: Path) -> None:
    status_dir = tmp_path / "status"
    assert system.create_backup_request(status_dir) is True
    assert system.create_backup_request(status_dir) is False
