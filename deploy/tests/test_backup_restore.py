"""Setup, backup and restore against the real image (OPS-01/07/08/10, PLT-06, plan §§ 11.2-11.6).

A first card is set up (setup.sh without the system steps), filled with demo data and backed
up. The snapshot is then restored onto a fresh second card that has stale -wal/-shm files lying
around, the way `setup.sh --restore` runs after an SD card swap. The first card is stopped
before (never run both cards) and the second one takes over its address.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
from pathlib import Path

import pytest

from conftest import APP_UID, DEPLOY, Images, Registry, run, tree

pytestmark = pytest.mark.docker

PORT = 18110


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_stale_wal(database: Path, tmp_path: Path) -> Path:
    copy = tmp_path / "stale.sqlite3"
    shutil.copy(database, copy)
    db = sqlite3.connect(copy)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("CREATE TABLE stale_marker (x)")
    db.execute("INSERT INTO stale_marker VALUES (1)")
    db.commit()
    wal = tmp_path / "stale.db-wal"
    shutil.copy(copy.with_name("stale.sqlite3-wal"), wal)
    db.close()
    assert wal.stat().st_size > 0
    return wal


def status_mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_setup_backup_and_restore_round_trip(
    make_pi, images: Images, registry: Registry, tmp_path: Path
) -> None:
    repository = "mealmate-restore"
    digest = registry.push(images.good, repository)

    # --- First card: setup.sh (steps 5-9), demo data, backup ----------------------------------
    old = make_pi("restore-old", PORT, repository)
    old.setup("--version", "2.0.0-alpha.1")
    assert old.pinned() == f"IMAGE_REF={old.image}@{digest}"
    assert old.container_image() == f"{old.image}@{digest}"
    for script in ("mm-compose", "backup.sh", "update.sh", "heartbeat.sh", "disk-check.sh",
                   "setup.sh", "prune.py"):  # fmt: skip
        assert (old.root / "bin" / script).is_file()
    calls = old.calls()
    assert any(c.startswith("cosign verify-attestation --type slsaprovenance1") for c in calls)
    assert "tailscale serve --bg --https=443 http://127.0.0.1:8080" in calls
    assert not any(c.startswith("tailscale up") for c in calls), "already logged in"
    assert any(c.startswith("systemctl enable --now") for c in calls)
    assert (old.data.stat().st_uid, status_mode(old.data)) == (APP_UID, 0o750)
    assert status_mode(old.state) == 0o700 and (old.state / "override.env").is_file()

    old.app("mealmate", "seed-demo")
    counts = old.counts()
    assert counts["users"] >= 4 and counts["meals"] > 0
    media_before = tree(old.data / "media")
    assert media_before, "seed-demo stores meal photos"

    first = old.script("backup.sh").stdout.strip().splitlines()[-1]
    second = old.script("backup.sh").stdout.strip().splitlines()[-1]
    snapshot = old.backups / second
    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["snapshot"] == second and manifest["label"] == "regular"
    assert manifest["image_digest"] == digest
    version = run(
        ["docker", "image", "inspect", images.good, "--format",
         '{{index .Config.Labels "org.opencontainers.image.version"}}'],
    ).stdout.strip()  # fmt: skip
    assert manifest["app_version"] == version
    assert manifest["db_sha256"] == sha256(snapshot / "db.sqlite3")
    assert manifest["media_files"] == len(media_before)
    assert set(manifest["files"]) >= {
        "secrets/env",
        "secrets/tailscaled.state",
        "secrets/ssh/ssh_host_ed25519_key",
        "secrets/mmbackup_authorized_keys",
    }
    assert tree(snapshot / "media") == media_before
    # Unchanged photos are hard links into the previous snapshot (OPS-01).
    some = next(iter(media_before))
    assert (snapshot / "media" / some).stat().st_ino == (
        old.backups / first / "media" / some
    ).stat().st_ino
    assert status_mode(snapshot / "secrets" / "env") == 0o640
    assert not list(old.backups.glob(".partial-*"))
    assert not (old.data / "status" / "backup.sqlite3").exists()

    status = old.backup_status()
    assert status["ok"] is True and status["label"] == "regular"
    assert status["snapshot"] == second and status["size_bytes"] > 0
    assert status["finished_at"].endswith("Z") and isinstance(status["message"], str)
    assert status_mode(old.state / "status" / "backup.json") == 0o644
    assert old.hc.last(old.check("backup")).path == f"/{old.check('backup')}"

    old.script("backup.sh", "--verify-latest")
    assert "verified" in old.hc.last(old.check("backup")).body

    # A WAL with committed frames (it creates the table stale_marker), planted on the new card
    # below. If the restore left it next to the restored database, SQLite would replay it.
    wal = make_stale_wal(snapshot / "db.sqlite3", tmp_path)

    # --- Planned swap: the old card is shut down, the snapshot copied over (scp -r) -----------
    old.compose("stop")
    copied = tmp_path / "from-mac" / second
    shutil.copytree(snapshot, copied)

    new = make_pi("restore-new", PORT, repository, env_file=False)
    new.data.mkdir(mode=0o750)
    os.chown(new.data, APP_UID, APP_UID)
    for suffix in ("-wal", "-shm"):
        target = new.data / f"mealmate.db{suffix}"
        shutil.copy(wal, target)
        os.chown(target, APP_UID, APP_UID)

    # A freshly flashed card has neither jq nor sqlite3, which the snapshot checks need before
    # step 1: they are hidden (bind mounts in a private mount namespace) until the package step
    # "installs" them (the apt-get shim unmounts them).
    hidden = " ".join(shutil.which(t) or t for t in ("jq", "sqlite3"))
    run(
        ["unshare", "--mount", "--propagation", "private", "sh", "-c",
         'for t in $MM_TEST_HIDDEN; do mount --bind /dev/null "$t"; done; exec "$@"', "sh",
         "bash", DEPLOY / "pi" / "setup.sh", "--skip-system",
         "--version", "2.0.0-alpha.1", "--restore", copied],
        env={**new.env, "MM_TEST_HIDDEN": hidden},
    )  # fmt: skip
    assert "apt-get -y install jq sqlite3" in new.calls()

    # Tailscale identity first, without ever logging in (O-1).
    calls = new.calls()
    stop, start = (
        calls.index("systemctl stop tailscaled"),
        calls.index("systemctl start tailscaled"),
    )
    assert stop < start
    assert not any(c.startswith("tailscale up") for c in calls)
    ts = Path(new.env["MEALMATE_TAILSCALE_STATE_DIR"]) / "tailscaled.state"
    assert ts.read_bytes() == (copied / "secrets" / "tailscaled.state").read_bytes()
    # SSH host keys, the backup key and .env.
    ssh = Path(new.env["MEALMATE_SSH_DIR"])
    old_ssh = Path(old.env["MEALMATE_SSH_DIR"])
    assert (ssh / "ssh_host_ed25519_key").read_bytes() == (
        old_ssh / "ssh_host_ed25519_key"
    ).read_bytes()
    assert status_mode(ssh / "ssh_host_ed25519_key") == 0o600
    keys = Path(new.env["MEALMATE_BACKUP_HOME"]) / ".ssh" / "authorized_keys"
    assert (
        keys.read_text()
        == (Path(old.env["MEALMATE_BACKUP_HOME"]) / ".ssh" / "authorized_keys").read_text()
    )
    assert (new.root / ".env").read_bytes() == (old.root / ".env").read_bytes()
    assert status_mode(new.root / ".env") == 0o600

    # The data: same rows, same photos, owned by the app user, stale WAL gone.
    assert new.container_image() == f"{new.image}@{digest}"
    assert new.counts() == counts
    assert tree(new.data / "media") == media_before
    for path in [new.data / "mealmate.db", new.data / "media", *(new.data / "media").rglob("*")]:
        assert path.stat().st_uid == APP_UID, path
    stale = new.data / "mealmate.db-wal"
    assert not stale.exists() or stale.read_bytes() != wal.read_bytes()
    assert "stale_marker" not in counts and "stale_marker" not in new.counts()
    assert (new.state / "restored-from").read_text().strip() == second

    # Re-running the same restore does not roll the data back again.
    new.app("mealmate", "reset-link", "admin")
    before = new.counts()
    new.setup("--restore", str(copied))
    assert new.counts() == before


def test_backup_timer_retention_and_status_files(make_pi, images: Images, registry: Registry):
    """Labelled backups, retention via prune.py, disk.json and the heartbeat."""
    repository = "mealmate-status"
    registry.push(images.good, repository)
    pi = make_pi("status", PORT + 1, repository)
    pi.setup("--version", "2.0-pre")

    # Old snapshots from a year of backups; the retention trims them after the next backup.
    assert not list(pi.backups.iterdir())
    first = pi.script("backup.sh", "--label", "pre-update").stdout.strip().splitlines()[-1]
    source = pi.backups / first
    for days in range(10, 400, 3):
        name = run(["date", "-u", "-d", f"-{days} days", "+%Y%m%dT%H%M%SZ"]).stdout.strip()
        shutil.copytree(source, pi.backups / name, symlinks=True)
        manifest = json.loads((source / "manifest.json").read_text())
        (pi.backups / name / "manifest.json").write_text(
            json.dumps({**manifest, "label": "regular"})
        )
    (pi.backups / ".partial-20200101T000000Z").mkdir()
    latest = pi.script("backup.sh", "--label", "manual").stdout.strip().splitlines()[-1]
    names = sorted(p.name for p in pi.backups.iterdir() if not p.name.startswith("."))
    assert first in names and latest in names
    assert len(names) <= 2 + 17
    assert not (pi.backups / ".partial-20200101T000000Z").exists()
    assert json.loads((pi.backups / latest / "manifest.json").read_text())["label"] == "manual"
    assert pi.backup_status()["label"] == "manual"

    pi.script("disk-check.sh", MEALMATE_DISK_MIN_FREE_PERCENT="0")
    disk = json.loads((pi.state / "status" / "disk.json").read_text())
    assert set(disk) == {"checked_at", "free_bytes", "total_bytes", "free_percent"}
    assert 0 < disk["free_bytes"] <= disk["total_bytes"] and 0 <= disk["free_percent"] <= 100
    assert pi.hc.last(pi.check("disk")).path == f"/{pi.check('disk')}"
    assert pi.script("disk-check.sh", check=False, MEALMATE_DISK_MIN_FREE_PERCENT="101").returncode
    assert pi.hc.last(pi.check("disk")).path.endswith("/fail")

    # The status files are what the app sees at /status (read-only).
    seen = pi.app("cat", "/status/backup.json").stdout
    assert json.loads(seen)["snapshot"] == latest
    assert pi.app("sh", "-c", "echo x > /status/probe", check=False).returncode != 0

    pi.script("heartbeat.sh")
    assert pi.hc.last(pi.check("heartbeat")).path == f"/{pi.check('heartbeat')}"
    down = pi.script(
        "heartbeat.sh", check=False, MM_TEST_TS_STATE="Stopped",
        MEALMATE_HEARTBEAT_RETRY_DELAY="0",
    )  # fmt: skip
    assert down.returncode == 1
    ping = pi.hc.last(pi.check("heartbeat"))
    assert ping.path.endswith("/fail") and "tailscale" in ping.body

    # Rotating the secret key restarts the app with the new key.
    key = (pi.root / ".env").read_text()
    pi.setup("--rotate-secret")
    assert (pi.root / ".env").read_text() != key
    run(["curl", "-fsS", "--noproxy", "*", f"http://127.0.0.1:{pi.port}/api/health"])
