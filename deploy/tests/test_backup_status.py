"""backup.sh's status file after a failed run, without Docker (ADM-01, OPS-01/08).

`backup.json` says when the last successful backup finished, also after runs that failed: the
previous status file's value, else the newest snapshot on disk. Here no app is running, so every
run fails at its first step; test_backup_restore.py covers a successful run against the image.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from conftest import DEPLOY, run

pytestmark = pytest.mark.root

KEYS = {"finished_at", "label", "ok", "snapshot", "size_bytes", "message", "last_success_at"}
# backup.json as a successful run wrote it.
SUCCEEDED = {
    "finished_at": "2026-09-27T12:15:04Z",
    "label": "regular",
    "ok": True,
    "snapshot": "20260927T121500Z",
    "size_bytes": 12345,
    "message": "backup 20260927T121500Z (regular) complete",
    "last_success_at": "2026-09-27T12:15:04Z",
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "srv"
    (root / "state" / "status").mkdir(parents=True)
    (root / "backups").mkdir()
    return root


def status_file(root: Path) -> Path:
    return root / "state" / "status" / "backup.json"


def failed_backup(root: Path, *args: str) -> dict:
    """Runs backup.sh, which fails without an app, and returns the backup.json it wrote."""
    result = run(
        ["bash", DEPLOY / "pi" / "bin" / "backup.sh", *args],
        env={**os.environ, "MEALMATE_ROOT": str(root), "MEALMATE_BACKUP_GROUP": "root"},
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert "is the app running?" in result.stderr
    path = status_file(root)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert not list(path.parent.glob(".mm-tmp.*")) and not list(root.glob("state/.mm-tmp.*"))
    status = json.loads(path.read_text(encoding="utf-8"))
    assert set(status) == KEYS
    assert status["ok"] is False and status["snapshot"] is None and status["size_bytes"] is None
    return status


def snapshot(root: Path, name: str) -> None:
    (root / "backups" / name).mkdir()


def test_a_failed_run_keeps_the_last_successful_backup(root: Path) -> None:
    status_file(root).write_text(json.dumps(SUCCEEDED), encoding="utf-8")
    snapshot(root, "20260927T121500Z")

    first = failed_backup(root, "--label", "manual")
    assert first["label"] == "manual" and first["finished_at"] != SUCCEEDED["finished_at"]
    assert first["last_success_at"] == SUCCEEDED["last_success_at"]
    # Carried over from one failed run to the next.
    assert failed_backup(root)["last_success_at"] == SUCCEEDED["last_success_at"]


@pytest.mark.parametrize(
    "previous",
    [
        None,
        # Written before backup.json had the key: the snapshots on disk tell instead.
        json.dumps({key: value for key, value in SUCCEEDED.items() if key != "last_success_at"}),
        json.dumps(SUCCEEDED | {"last_success_at": None}),
        json.dumps(SUCCEEDED | {"last_success_at": "yesterday"}),
        json.dumps(SUCCEEDED | {"last_success_at": 1760680841}),
        json.dumps(SUCCEEDED)[:-1],
    ],
    ids=["no status", "old status", "null", "not a time", "a number", "not json"],
)
def test_without_an_earlier_value_a_failed_run_takes_the_newest_snapshot(
    root: Path, previous: str | None
) -> None:
    if previous is not None:
        status_file(root).write_text(previous, encoding="utf-8")
    for name in ("20261016T120002Z", "20261015T000001Z"):
        snapshot(root, name)
    # Neither an unfinished snapshot nor anything else counts.
    for name in (".partial-20261018T000000Z", "20261019T000000Z.old"):
        snapshot(root, name)
    (root / "backups" / "20261020T000000Z").write_text("not a snapshot directory")

    assert failed_backup(root)["last_success_at"] == "2026-10-16T12:00:02Z"


def test_a_first_failed_run_without_snapshots_leaves_it_empty(root: Path) -> None:
    status = failed_backup(root)
    assert status["last_success_at"] is None
    assert failed_backup(root)["last_success_at"] is None
