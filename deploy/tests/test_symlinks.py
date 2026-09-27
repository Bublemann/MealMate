"""Host scripts run as root and never follow symlinks in the container-writable data/ (SEC-09,
plan § 11.1). A compromised container is simulated by a docker wrapper that, right after the
app's `backup-db`, swaps the database copy for a symlink to a host file or a hard link.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from conftest import APP_UID, Images, Registry, run

pytestmark = pytest.mark.docker

PORT = 18130

EVIL_DOCKER = """#!/bin/sh
# docker, but the "container" plants something in data/status after backup-db.
docker "$@"
status=$?
copy="$MEALMATE_ROOT/data/status/backup.sqlite3"
case " $* " in
  *" backup-db "*)
    case "$MM_TEST_EVIL" in
      symlink) rm -f "$copy"; ln -s "$MM_TEST_EVIL_TARGET" "$copy" ;;
      hardlink) rm -f "$copy"; ln "$MEALMATE_ROOT/data/mealmate.db" "$copy" ;;
    esac
    ;;
esac
exit $status
"""


def test_planted_symlinks_and_hard_links_are_never_followed(
    make_pi, images: Images, registry: Registry, tmp_path: Path
) -> None:
    repository = "mealmate-symlinks"
    registry.push(images.good, repository)
    pi = make_pi("symlinks", PORT, repository)
    pi.setup("--version", "2.0-pre")
    backup_check = pi.check("backup")
    evil = tmp_path / "docker"
    evil.write_text(EVIL_DOCKER)
    evil.chmod(0o755)
    secret = tmp_path / "host-secret"
    secret.write_text("root-only host secret\n")
    secret.chmod(0o600)

    def snapshots() -> set[str]:
        return {p.name for p in pi.backups.iterdir()}

    # backup.sqlite3 swapped for a symlink to a host file: refused, nothing copied.
    before = snapshots()
    result = pi.script(
        "backup.sh", check=False, DOCKER=str(evil), MM_TEST_EVIL="symlink",
        MM_TEST_EVIL_TARGET=str(secret),
    )  # fmt: skip
    assert result.returncode == 1
    assert "symlink or hard link" in result.stderr
    assert snapshots() == before
    for path in pi.backups.rglob("*"):
        assert not path.is_file() or b"root-only host secret" not in path.read_bytes()
    assert secret.read_text() == "root-only host secret\n" and secret.stat().st_uid == 0
    status = pi.backup_status()
    assert status["ok"] is False and status["snapshot"] is None and status["size_bytes"] is None
    assert "symlink or hard link" in status["message"]
    assert pi.hc.last(backup_check).path.endswith("/fail")

    # backup.sqlite3 as a hard link to the live database: refused, the database keeps its owner.
    result = pi.script(
        "backup.sh", check=False, DOCKER=str(evil), MM_TEST_EVIL="hardlink",
    )  # fmt: skip
    assert result.returncode == 1
    assert snapshots() == before
    assert (pi.data / "mealmate.db").stat().st_uid == APP_UID
    run(["curl", "-fsS", "--noproxy", "*", f"http://127.0.0.1:{PORT}/api/health"])

    # The admin page's request file as a symlink to a host file: removed, never followed.
    request = pi.data / "status" / "backup-request"
    request.symlink_to(secret)
    pi.script("backup.sh", "--label", "manual")
    assert not request.exists() and not request.is_symlink()
    assert secret.read_text() == "root-only host secret\n"
    assert pi.backup_status()["label"] == "manual" and pi.backup_status()["ok"] is True

    # Whatever a path in data/media leads to (a directory swapped for a symlink while rsync
    # walks it would do), the photos are read with the app user's rights only: a root-only
    # file there is never copied into a snapshot, and the backup fails loudly.
    hidden = pi.data / "media" / "host-only"
    hidden.mkdir(mode=0o700)
    (hidden / "photo.jpg").write_text("root-only host secret\n")
    (hidden / "photo.jpg").chmod(0o600)
    before = snapshots()
    result = pi.script("backup.sh", check=False)
    assert result.returncode == 1
    assert "copying the photos as the app user (uid 10001) failed" in result.stderr
    assert snapshots() == before
    for path in [*pi.backups.rglob("*"), *(pi.root / "media-mirror").rglob("*")]:
        assert not path.is_file() or b"root-only host secret" not in path.read_bytes()
    assert (pi.root / "media-mirror").stat().st_uid == APP_UID
    shutil.rmtree(hidden)
    pi.script("backup.sh")

    # data/status itself as a symlink to a host directory: nothing inside it is touched.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "backup-request").write_text("keep me\n")
    os.rename(pi.data / "status", tmp_path / "real-status")
    (pi.data / "status").symlink_to(elsewhere)
    result = pi.script("backup.sh", "--label", "manual", check=False)
    assert result.returncode == 1
    assert (elsewhere / "backup-request").read_text() == "keep me\n"
    assert sorted(p.name for p in elsewhere.iterdir()) == ["backup-request"]
