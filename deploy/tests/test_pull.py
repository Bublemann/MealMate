"""The Mac's pull.sh (OPS-03, plan § 11.3), run with bash 3.2 against a fake Pi.

The fake Pi is a local directory (rsync's local mode stands in for rsync over SSH to rrsync,
which the owner checks on the real Pi, O-5). Everything else is the real script.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from conftest import DEPLOY, HealthchecksServer, run

PULL = DEPLOY / "mac" / "pull.sh"


def stamp(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


class FakePi:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir()
        self.counter = 0

    def snapshot(self, *, media: dict[str, bytes] | None = None, db: bytes | None = None,
                 bad_checksum: bool = False, distinct_times: bool = True) -> str:  # fmt: skip
        self.counter += 1
        sid = stamp(datetime(2026, 9, 1, tzinfo=UTC) + timedelta(hours=6 * self.counter))
        directory = self.root / sid
        (directory / "media").mkdir(parents=True)
        (directory / "secrets").mkdir()
        db = db if db is not None else f"database {sid}".encode()
        (directory / "db.sqlite3").write_bytes(db)
        (directory / "secrets" / "env").write_text("MEALMATE_SECRET_KEY=x\n")
        for name, content in (media or {}).items():
            path = directory / "media" / name
            path.write_bytes(content)
            os.utime(path, (1_700_000_000, 1_700_000_000))
        digest = hashlib.sha256(db).hexdigest()
        manifest = {
            "snapshot": sid,
            "label": "regular",
            "db_sha256": "0" * 64 if bad_checksum else digest,
        }
        (directory / "manifest.json").write_text(json.dumps(manifest))
        if distinct_times:  # as on the Pi, where snapshots are hours apart
            when = 1_700_000_000 + 21_600 * self.counter
            for name in ("manifest.json", "db.sqlite3", "secrets/env"):
                os.utime(directory / name, (when, when))
        return sid


class Mac:
    def __init__(self, base: Path, remote: FakePi, hc: HealthchecksServer, bash: str) -> None:
        self.base, self.remote, self.hc, self.bash = base, remote, hc, bash
        self.dest = base / "MealMateBackups"
        self.check = f"mac-{base.name}"
        self.config = base / "config"
        self.values = {
            "MM_REMOTE": f"{remote.root}/",
            "MM_DEST": str(self.dest),
            "MM_RSYNC": "rsync",
            "MM_PYTHON": sys.executable,
            "MM_PRUNE": str(DEPLOY / "common" / "prune.py"),
            "MM_RSYNC_MIN_VERSION": "3.1.0",
            "MM_LOG": str(base / "pull.log"),
            "HC_MACPULL_URL": hc.url(self.check),
        }
        self.write_config()

    def write_config(self, **changes: str) -> None:
        self.values.update(changes)
        self.config.write_text("".join(f"{k}='{v}'\n" for k, v in self.values.items()))

    def pull(self, *args: str, expect: int = 0):
        env = {**os.environ, "MM_PULL_CONFIG": str(self.config), "HOME": str(self.base)}
        result = run([self.bash, PULL, *args], env=env, check=False)
        assert result.returncode == expect, result.stderr
        return result

    @property
    def snapshots(self) -> list[Path]:
        directory = self.dest / "snapshots"
        return sorted(directory.iterdir()) if directory.exists() else []

    def ledger(self) -> list[list[str]]:
        path = self.dest / "pulled.txt"
        return [line.split() for line in path.read_text().splitlines()] if path.exists() else []

    def last_ping(self):
        return self.hc.last(self.check)


@pytest.fixture
def mac(tmp_path: Path, hc: HealthchecksServer, mac_bash: str) -> Mac:
    return Mac(tmp_path, FakePi(tmp_path / "pi-backups"), hc, mac_bash)


def test_first_pull_ledger_and_untrusted_names(mac: Mac) -> None:
    photo = b"photo" * 1000
    pi = mac.remote
    first = pi.snapshot(media={"a.jpg": photo})
    (pi.root / first / "media" / "passwd").symlink_to("/etc/passwd")
    second = pi.snapshot(media={"a.jpg": photo})
    with (pi.root / second / "media" / "huge.bin").open("wb") as handle:
        handle.truncate(51 * 1024 * 1024)
    third = pi.snapshot(media={"a.jpg": photo, "b.jpg": b"new"})
    for odd in (".partial-20260927T000000Z", "evil name", "20260101T000000Z.bak", "$(reboot)"):
        (pi.root / odd).mkdir()
    (pi.root / "20250101T000000Z").symlink_to(pi.root / first)
    (pi.root / "20250202T000000Z").write_text("not a directory")

    result = mac.pull()
    assert "ignored 3 unexpected names" in result.stderr
    assert [row[0] for row in mac.ledger()] == [first, second, third]
    local = mac.snapshots
    assert len(local) == 3
    # Stored under the Mac's receive time, not under the Pi's names.
    assert {p.name for p in local}.isdisjoint({first, second, third})
    assert [row[1] for row in mac.ledger()] == [p.name for p in local]
    for directory, sid in zip(local, (first, second, third), strict=True):
        assert json.loads((directory / "manifest.json").read_text())["snapshot"] == sid
    inodes = {(p / "media" / "a.jpg").stat().st_ino for p in local}
    assert len(inodes) == 1, "unchanged photos are hard links to the previous snapshot"
    assert (
        not (local[0] / "media" / "passwd").exists()
        and not (local[0] / "media" / "passwd").is_symlink()
    )
    assert not (local[1] / "media" / "huge.bin").exists(), "--max-size=50M"
    assert (local[2] / "media" / "b.jpg").read_bytes() == b"new"
    assert not (mac.dest / ".staging").exists()
    assert mac.last_ping().path == f"/{mac.check}"

    # A compromised Pi rewrites a snapshot the Mac already has: it is never fetched again.
    (pi.root / first / "db.sqlite3").write_bytes(b"ransom")
    mac.pull()
    assert len(mac.snapshots) == 3
    assert (local[0] / "db.sqlite3").read_bytes() == f"database {first}".encode()


def test_a_snapshot_that_fails_its_checksum_is_rejected_once(mac: Mac) -> None:
    good = mac.remote.snapshot()
    mac.pull()
    bad = mac.remote.snapshot(bad_checksum=True)
    mac.pull(expect=1)
    assert mac.last_ping().path.endswith("/fail")
    assert "rejected" in mac.last_ping().body
    assert mac.ledger()[-1][:2] == [bad, "rejected"]
    assert len(mac.snapshots) == 1
    mac.pull()
    assert mac.last_ping().path == f"/{mac.check}"
    assert [row[0] for row in mac.ledger()] == [good, bad]


def test_abnormal_count_stops_without_pruning_until_accepted(mac: Mac) -> None:
    mac.remote.snapshot()
    mac.pull()
    old = mac.dest / "snapshots" / stamp(datetime.now(UTC) - timedelta(days=300))
    old.mkdir()
    (old / "db.sqlite3").write_bytes(b"old")
    (old / "keep").write_text("x")
    older = mac.dest / "snapshots" / stamp(datetime.now(UTC) - timedelta(days=300, hours=1))
    older.mkdir()
    new_ids = [mac.remote.snapshot() for _ in range(9)]  # limit: 8 + 5 x ~0 days

    result = mac.pull(expect=1)
    assert "abnormal pull: 9 new snapshots (limit 8)" in result.stderr
    assert mac.last_ping().path.endswith("/fail")
    assert older.exists(), "an abnormal pull must not prune"
    assert len(mac.ledger()) == 1

    mac.pull("--accept-abnormal")
    assert [row[0] for row in mac.ledger()][1:] == new_ids
    assert not older.exists(), "pruned after the accepted pull"
    assert mac.last_ping().path == f"/{mac.check}"


def test_the_limit_grows_with_the_days_since_the_last_pull(mac: Mac) -> None:
    mac.remote.snapshot()
    mac.pull()
    (mac.dest / ".state" / "last-success").write_text(f"{int(time.time()) - 2 * 86400}\n")
    for _ in range(12):  # limit: 8 + 5 x 2 days = 18
        mac.remote.snapshot()
    mac.pull()
    assert len(mac.ledger()) == 13


def test_abnormal_size_stops(mac: Mac) -> None:
    mac.remote.snapshot()
    mac.pull()
    mac.write_config(MM_MAX_BYTES="4000")
    mac.remote.snapshot(db=b"x" * 5000)
    result = mac.pull(expect=1)
    abnormal = r"abnormal pull: (\d+) bytes in 1 new snapshots \(limit 4000\)"
    found = re.search(abnormal, result.stderr)
    assert found, result.stderr
    assert 5000 < int(found.group(1)) < 6000, "the database plus a manifest and .env"
    assert len(mac.ledger()) == 1


def test_first_pull_into_an_empty_ledger_is_exempt(mac: Mac) -> None:
    """A new Mac (OPS-10) fetches everything the Pi has."""
    for _ in range(12):
        mac.remote.snapshot()
    mac.pull()
    assert len(mac.ledger()) == 12


def test_prune_by_receive_time_never_below_seven_days(mac: Mac) -> None:
    now = datetime.now(UTC)
    for days in range(1, 120):
        directory = mac.dest / "snapshots" / stamp(now - timedelta(days=days, minutes=5))
        directory.mkdir(parents=True)
    mac.remote.snapshot()
    mac.pull()
    names = {p.name for p in mac.snapshots}
    young = {stamp(now - timedelta(days=d, minutes=5)) for d in range(1, 7)}
    assert young <= names
    assert 12 <= len(names) <= 20


def test_old_rsync_is_refused(mac: Mac) -> None:
    mac.write_config(MM_RSYNC_MIN_VERSION="99.0.0")
    result = mac.pull(expect=1)
    assert "too old" in result.stderr
    assert mac.last_ping().path.endswith("/fail")


def test_a_file_that_only_looks_unchanged_is_fetched_again(mac: Mac) -> None:
    """Same size and time as in the previous snapshot, different content: the hard link that
    rsync's quick check would make fails the manifest check, and the full fetch fixes it."""
    first = mac.remote.snapshot(db=b"A" * 100, distinct_times=False)
    second = mac.remote.snapshot(db=b"B" * 100, distinct_times=False)
    for sid in (first, second):
        for name in ("db.sqlite3", "manifest.json"):
            os.utime(mac.remote.root / sid / name, (1_700_000_000, 1_700_000_000))
    mac.pull()
    local = mac.snapshots
    assert [(p / "db.sqlite3").read_bytes() for p in local] == [b"A" * 100, b"B" * 100]
    assert [row[0] for row in mac.ledger()] == [first, second]
