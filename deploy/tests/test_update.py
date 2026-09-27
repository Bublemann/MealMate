"""update.sh: verification, pre-update backup, automatic rollback, recovery (OPS-05/06, PLT-03/07,
SEC-12, plan § 11.5), and what setup.sh does to the version on a re-run.

The registry tag 2.0-pre first points to a good image, then to a deliberately broken one (it
migrates the database to an unknown revision, changes the sentinel row, adds a table, plants
symlinks and never becomes healthy), then to a new good digest, then to one that is healthy for
a moment only, then to one whose provenance cannot be checked (network) and finally to one
without valid provenance (the cosign shim fails).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from conftest import COSIGN_NETWORK_ERROR, Images, Pi, Registry, run

pytestmark = pytest.mark.docker

PORT = 18120
SENTINEL = "SELECT display_name FROM users WHERE username = 'admin'"
REVISION = "SELECT version_num FROM alembic_version"
TABLES = "SELECT name FROM sqlite_master WHERE type = 'table'"


# docker and curl as the scripts see them, with one fault injected (the rest is real):
# MM_TEST_ON_STOP=break-snapshot: at `mm-compose stop` (the rollback's first Compose step), every
#   snapshot's db.sqlite3 becomes a directory, so copying it back fails;
# MM_TEST_ON_STOP=public-down: from `mm-compose stop` on, the public health URL fails (a
#   Tailscale problem that has nothing to do with the new version).
# MM_TEST_UP_LOG: at each `mm-compose up`, whether a mealmate.db-journal is lying in data/.
FAULTY_DOCKER = """#!/bin/sh
journal="$MEALMATE_ROOT/data/mealmate.db-journal"
case " $* " in
  *" compose "*" stop "*)
    case "$MM_TEST_ON_STOP" in
      break-snapshot)
        for db in "$MEALMATE_ROOT"/backups/*/db.sqlite3; do rm -f "$db"; mkdir "$db"; done ;;
      public-down) touch "$MM_TEST_FLAG" ;;
    esac ;;
  *" compose "*" up "*)
    if [ -n "$MM_TEST_UP_LOG" ]; then
      if [ -e "$journal" ] || [ -L "$journal" ]; then echo journal; else echo clean; fi \
        >>"$MM_TEST_UP_LOG"
    fi ;;
esac
exec docker "$@"
"""
FAULTY_CURL = """#!/bin/sh
if [ -e "$MM_TEST_FLAG" ]; then
  case " $* " in *"$MM_TEST_PUBLIC_HOST"*) echo "curl: (7) Failed to connect" >&2; exit 7 ;; esac
fi
exec curl "$@"
"""

# curl whose health checks fail while MM_TEST_BLOCK is the pinned digest.
BLIND_CURL = """#!/bin/sh
case " $* " in
  *"/api/health"*)
    if grep -q "$MM_TEST_BLOCK" "$MEALMATE_ROOT/state/override.env"; then exit 7; fi ;;
esac
exec curl "$@"
"""


def tool(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text)
    path.chmod(0o755)
    return str(path)


def local_digests(pi: Pi) -> set[str]:
    out = run(
        ["docker", "image", "ls", "--digests", "--format", "{{.Digest}}", pi.image]
    ).stdout.split()
    return {d for d in out if d.startswith("sha256:")}


def test_rollback_then_recovery_then_unverifiable(
    make_pi, images: Images, registry: Registry
) -> None:
    repository = "mealmate-update"
    good = registry.push(images.good, repository)
    pi = make_pi("update", PORT, repository)
    pi.setup("--version", "2.0.0-alpha.1")
    pi.app("mealmate", "seed-demo")
    sentinel, revision = pi.query(SENTINEL), pi.query(REVISION)
    counts = pi.counts()
    update_check = pi.check("update")
    victim = pi.base / "victim"
    victim_text = victim.read_text()

    # Nothing new: success, nothing happens.
    pi.script("update.sh")
    assert pi.hc.last(update_check).path == f"/{update_check}"
    assert "up to date" in pi.hc.last(update_check).body

    # --- A broken release: rolled back automatically -------------------------------------------
    bad = registry.push(images.bad, repository)
    result = pi.script("update.sh", check=False, MEALMATE_HEALTH_TIMEOUT="25")
    assert result.returncode == 1, result.stderr

    assert (pi.data / "bad-image-ran").exists(), "the bad image did run and damage the data"
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good}"
    assert pi.container_image() == f"{pi.image}@{good}"
    run(["curl", "-fsS", "--noproxy", "*", f"http://127.0.0.1:{PORT}/api/health"])
    assert pi.query(REVISION) == revision, "the schema revision is the one before the update"
    assert pi.query(SENTINEL) == sentinel, "the sentinel row is the one before the update"
    assert "bad_image_marker" not in {row[0] for row in pi.query(TABLES)}
    assert pi.counts() == counts
    assert (pi.state / "bad-digest").read_text().split() == [bad]
    assert (pi.state / "previous-digest").read_text().strip() == good
    assert victim.read_text() == victim_text, "a planted symlink was followed"
    assert not (pi.data / "mealmate.db").is_symlink()

    pre_update = [
        p for p in pi.backups.iterdir()
        if json.loads((p / "manifest.json").read_text())["label"] == "pre-update"
    ]  # fmt: skip
    assert len(pre_update) == 1
    assert json.loads((pre_update[0] / "manifest.json").read_text())["image_digest"] == good

    ping = pi.hc.last(update_check)
    assert ping.path == f"/{update_check}/fail"
    assert "rolling back" in ping.body and "rolled back" in ping.body
    assert f"revision {revision[0][0]} as in the snapshot" in ping.body

    # The same bad digest is not tried again.
    pi.script("update.sh")
    assert "rolled back before" in pi.hc.last(update_check).body
    assert pi.container_image() == f"{pi.image}@{good}"

    # --- A newer good digest on the tag: applied -----------------------------------------------
    host_file = pi.root / "bin" / "heartbeat.sh"
    host_file.write_text("# stale copy, replaced by the update\n")
    good2 = registry.push(images.good2, repository)
    pi.script("update.sh")
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good2}"
    assert pi.container_image() == f"{pi.image}@{good2}"
    assert (pi.state / "previous-digest").read_text().strip() == good
    assert pi.query(SENTINEL) == sentinel and pi.counts() == counts
    assert host_file.read_text().startswith("#!/usr/bin/env bash"), "host files from the image"
    assert local_digests(pi) == {good, good2}, "images other than current and previous removed"
    assert pi.hc.last(update_check).path == f"/{update_check}"

    # --- Healthy for a moment, then crashing (restarted by Docker): not stable, rolled back ----
    flaky = registry.push(images.flaky, repository)
    result = pi.script(
        "update.sh", check=False, MEALMATE_HEALTH_TIMEOUT="25",
        MEALMATE_HEALTH_STABLE_INTERVAL="3",
    )  # fmt: skip
    assert result.returncode == 1, result.stderr
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good2}"
    assert pi.container_image() == f"{pi.image}@{good2}"
    assert (pi.state / "bad-digest").read_text().split() == [bad, flaky]
    assert pi.query(SENTINEL) == sentinel and pi.counts() == counts
    assert "rollback to" in pi.hc.last(update_check).body

    # --- Provenance that cannot be checked (network): retried, not recorded, nothing deployed --
    good3 = registry.push(images.good3, repository)
    result = pi.script(
        "update.sh", check=False, MM_TEST_COSIGN="fail", MM_TEST_COSIGN_ERROR=COSIGN_NETWORK_ERROR
    )
    assert result.returncode == 1
    assert pi.container_image() == f"{pi.image}@{good2}"
    assert good3 not in (pi.state / "bad-digest").read_text().split()
    ping = pi.hc.last(update_check)
    assert ping.path.endswith("/fail") and "not recorded as bad" in ping.body
    assert COSIGN_NETWORK_ERROR in ping.body, "cosign's own error is in the alert"
    tries = [c for c in pi.calls() if c.endswith(f"@{good3}")]
    assert len(tries) == 3, "three attempts"
    assert good3 not in local_digests(pi), "nothing pulled"

    # --- No valid provenance: recorded as bad, nothing deployed --------------------------------
    result = pi.script("update.sh", check=False, MM_TEST_COSIGN="fail")
    assert result.returncode == 1
    assert pi.container_image() == f"{pi.image}@{good2}"
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good2}"
    assert (pi.state / "bad-digest").read_text().split() == [bad, flaky, good3]
    assert "not installed" in pi.hc.last(update_check).body
    ping = pi.hc.last(update_check)
    assert ping.path.endswith("/fail") and "provenance" in ping.body
    calls = [c for c in pi.calls() if c.startswith("cosign verify-attestation")]
    assert calls[-1] == (
        "cosign verify-attestation --type slsaprovenance1 --certificate-oidc-issuer "
        "https://token.actions.githubusercontent.com --certificate-identity-regexp "
        r"^https://github\.com/Bublemann/MealMate/\.github/workflows/build-image\.yml"
        rf"@refs/tags/v[0-9].*$ {pi.image}@{good3}"
    )


def test_update_refuses_without_a_rollback_target(
    make_pi, images: Images, registry: Registry
) -> None:
    """An unpinned installation whose running digest is unknown is not updated blindly."""
    repository = "mealmate-nopin"
    registry.push(images.good, repository)
    pi = make_pi("nopin", PORT + 1, repository)
    pi.setup("--version", "2.0-pre")
    (pi.state / "override.env").write_text("")
    run(["docker", "image", "rm", "--force", *[f"{pi.image}@{d}" for d in local_digests(pi)]])
    registry.push(images.good2, repository)
    result = pi.script("update.sh", check=False)
    assert result.returncode == 1
    assert "no rollback target" in pi.hc.last(pi.check("update")).body
    assert (pi.state / "override.env").read_text() == ""
    assert Path(pi.backups).is_dir() and not list(pi.backups.iterdir())


def seeded(make_pi, registry: Registry, images: Images, name: str, port: int):
    """A Pi on the good image with demo data; returns it, the good digest and the database facts
    a rollback must bring back."""
    repository = f"mealmate-{name}"
    good = registry.push(images.good, repository)
    pi = make_pi(name, port, repository)
    pi.setup("--version", "2.0-pre")
    pi.app("mealmate", "seed-demo")
    return pi, repository, good, (pi.query(SENTINEL), pi.query(REVISION), pi.counts())


def test_rollback_completes_when_restoring_the_database_fails(
    make_pi, images: Images, registry: Registry, tmp_path: Path
) -> None:
    """The copy of the snapshot database fails mid-rollback: the previous version is still
    pinned and started, the bad digest recorded, and the alert says what failed."""
    pi, repository, good, _ = seeded(make_pi, registry, images, "cpfail", PORT + 2)
    bad = registry.push(images.bad, repository)
    docker = tool(tmp_path, "docker", FAULTY_DOCKER)
    result = pi.script(
        "update.sh", check=False, DOCKER=docker, MM_TEST_ON_STOP="break-snapshot",
        MEALMATE_HEALTH_TIMEOUT="15",
    )  # fmt: skip
    assert result.returncode == 1, result.stderr
    assert "cp: " in result.stderr, "the copy really failed"
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good}"
    assert pi.container_image() == f"{pi.image}@{good}", "the previous version was started"
    assert (pi.state / "bad-digest").read_text().split() == [bad]
    assert not (pi.state / "update-in-progress").exists()
    ping = pi.hc.last(pi.check("update"))
    assert ping.path.endswith("/fail")
    assert "rollback to" in ping.body and "incomplete; failed: restoring the database" in ping.body


def test_an_interrupted_update_is_finished_by_the_next_run(
    make_pi, images: Images, registry: Registry, tmp_path: Path
) -> None:
    """update.sh killed while it waits for health: the next run rolls back a broken version,
    finishes a healthy one, and re-pins the previous one if the new one never started."""
    pi, repository, good, (sentinel, revision, counts) = seeded(
        make_pi, registry, images, "killed", PORT + 3
    )
    marker = pi.state / "update-in-progress"
    check = pi.check("update")

    def deployed(digest: str) -> bool:
        """The run under test has written its marker, pinned `digest` and started it."""
        pin = f"IMAGE_REF={pi.image}@{digest}"
        if not marker.exists() or pi.pinned() != pin:
            return False
        try:  # the container may be in the middle of being replaced
            return pi.container_image() == f"{pi.image}@{digest}"
        except AssertionError:
            return False

    def killed_while_waiting(digest: str, **env: str) -> None:
        with (tmp_path / "killed.log").open("w") as log:
            process = subprocess.Popen(
                ["bash", pi.root / "bin" / "update.sh"], env={**pi.env, **env},
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
            )  # fmt: skip
            deadline = time.monotonic() + 180
            while not deployed(digest):
                assert process.poll() is None, (tmp_path / "killed.log").read_text()
                assert time.monotonic() < deadline
                time.sleep(0.5)
            time.sleep(2)  # in the health wait
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        assert marker.exists()

    # A broken version: the killed run never got to roll back; the next run does.
    bad = registry.push(images.bad, repository)
    killed_while_waiting(bad, MEALMATE_HEALTH_TIMEOUT="600")
    assert (pi.data / "bad-image-ran").exists()
    result = pi.script("update.sh", check=False, MEALMATE_HEALTH_TIMEOUT="15")
    assert result.returncode == 1, result.stderr
    assert "did not finish" in result.stderr and "up to date" not in result.stderr
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good}"
    assert pi.container_image() == f"{pi.image}@{good}"
    assert pi.query(REVISION) == revision and pi.query(SENTINEL) == sentinel
    assert pi.counts() == counts
    assert (pi.state / "bad-digest").read_text().split() == [bad]
    assert not marker.exists()
    assert pi.hc.last(check).path.endswith("/fail")

    # A healthy version: the killed run did not see it; the next run finishes the update.
    good2 = registry.push(images.good2, repository)
    (pi.root / "bin" / "heartbeat.sh").write_text("# stale\n")
    # (The killed run cannot see the new version's health, so it is still waiting when killed.)
    blind = tool(tmp_path, "curl", BLIND_CURL)
    killed_while_waiting(good2, CURL=blind, MM_TEST_BLOCK=good2, MEALMATE_HEALTH_TIMEOUT="600")
    pi.script("update.sh")
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good2}"
    assert pi.container_image() == f"{pi.image}@{good2}"
    assert pi.query(SENTINEL) == sentinel, "no rollback of a healthy update's data"
    assert (pi.root / "bin" / "heartbeat.sh").read_text().startswith("#!/usr/bin/env bash")
    assert not marker.exists()
    assert "finishing that update" in pi.hc.last(check).body
    assert pi.hc.last(check).path == f"/{check}"

    # Cut short before the new version ever started (marker written, container unchanged):
    # back on the running version, nothing recorded, the next run tries again.
    good3 = registry.push(images.good3, repository)
    marker.write_text(f"digest={good3}\nprevious={good2}\nsnapshot=20260101T000000Z\n")
    (pi.state / "override.env").write_text(f"IMAGE_REF={pi.image}@{good3}\n")
    result = pi.script("update.sh", check=False)
    assert result.returncode == 1
    assert "the next run tries the update again" in result.stderr
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good2}"
    assert pi.query(SENTINEL) == sentinel
    assert good3 not in (pi.state / "bad-digest").read_text().split()
    assert not marker.exists()


def test_an_unhealthy_current_version_is_not_updated_and_elsewhere_problems_blacklist_nothing(
    make_pi, images: Images, registry: Registry, tmp_path: Path
) -> None:
    pi, repository, good, (sentinel, revision, _) = seeded(
        make_pi, registry, images, "gate", PORT + 4
    )
    check = pi.check("update")

    # Pre-update health gate: the running version is down, so nothing is touched.
    pi.compose("stop")
    registry.push(images.good2, repository)
    result = pi.script("update.sh", check=False, MEALMATE_PRECHECK_TIMEOUT="5")
    assert result.returncode == 1
    ping = pi.hc.last(check)
    assert ping.path.endswith("/fail") and "current version unhealthy, update skipped" in ping.body
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good}"
    assert local_digests(pi) == {good}, "the new version was not even pulled"
    assert not list(pi.backups.iterdir()) and not (pi.state / "bad-digest").exists()

    # The new version fails, and after the rollback the previous one fails the public check as
    # well: Tailscale (or the network) is the problem, so the new digest is not blacklisted. The
    # broken version also left a rollback journal (a symlink to a host file) that SQLite would
    # replay into the restored database: it is gone before the previous version starts.
    pi.compose("up", "-d")
    bad = registry.push(images.bad, repository)
    host = f"localhost:{pi.port}"
    env_file = pi.root / ".env"
    env_file.write_text(
        env_file.read_text().replace(
            f"MEALMATE_PUBLIC_URL=http://127.0.0.1:{pi.port}", f"MEALMATE_PUBLIC_URL=http://{host}"
        )
    )
    result = pi.script(
        "update.sh", check=False, DOCKER=tool(tmp_path, "docker", FAULTY_DOCKER),
        CURL=tool(tmp_path, "curl", FAULTY_CURL), MM_TEST_ON_STOP="public-down",
        MM_TEST_FLAG=str(tmp_path / "public-down"), MM_TEST_PUBLIC_HOST=host,
        MM_TEST_UP_LOG=str(tmp_path / "up.log"), MEALMATE_HEALTH_TIMEOUT="15",
    )  # fmt: skip
    assert result.returncode == 1, result.stderr
    assert (tmp_path / "public-down").exists()
    assert (tmp_path / "up.log").read_text().split() == ["clean", "clean"], "deploy, rollback"
    assert (pi.data / "bad-image-ran").exists()
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good}"
    assert pi.container_image() == f"{pi.image}@{good}"
    assert pi.query(REVISION) == revision and pi.query(SENTINEL) == sentinel
    assert bad not in (pi.state / "bad-digest").read_text().split()
    ping = pi.hc.last(check)
    assert ping.path.endswith("/fail") and "NOT recorded as bad" in ping.body


def test_rerunning_setup_keeps_the_installed_version(
    make_pi, images: Images, registry: Registry
) -> None:
    """Moving forward is update.sh's job: a re-run of setup.sh keeps the pinned digest even if
    the tag moved on, and never deploys a digest recorded as bad."""
    repository = "mealmate-rerun"
    good = registry.push(images.good, repository)
    pi = make_pi("rerun", PORT + 5, repository)
    pi.setup("--version", "2.0-pre")
    good2 = registry.push(images.good2, repository)

    stale = pi.root / "bin" / "heartbeat.sh"
    stale.write_text("# stale\n")
    result = pi.setup("--version", "2.0-pre")
    assert "keeping the installed version" in result.stderr
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good}"
    assert pi.container_image() == f"{pi.image}@{good}"
    assert local_digests(pi) == {good}, "the newer tag digest was not even pulled"
    assert stale.read_text().startswith("#!/usr/bin/env bash"), "host files reinstalled"

    # The pinned image is gone locally: pulled again by digest (verified), not the tag.
    def verifications() -> int:
        return sum(1 for c in pi.calls() if c.startswith("cosign") and c.endswith(f"@{good}"))

    pi.compose("down")
    run(["docker", "image", "rm", f"{pi.image}@{good}"])
    before = verifications()
    pi.setup()
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good}"
    assert pi.container_image() == f"{pi.image}@{good}"
    assert verifications() == before + 1

    # An emptied pin: the running image's digest is pinned again.
    (pi.state / "override.env").write_text("")
    pi.setup()
    assert pi.pinned() == f"IMAGE_REF={pi.image}@{good}"

    # Nothing installed and the tag points to a digest recorded as bad: refused.
    pi.compose("down")
    run(["docker", "image", "rm", f"{pi.image}@{good}"])
    (pi.state / "override.env").write_text("")
    (pi.state / "bad-digest").write_text(f"{good2}\n")
    result = pi.setup(check=False)
    assert result.returncode == 1 and "listed in state/bad-digest" in result.stderr
    assert (pi.state / "override.env").read_text() == ""
    assert local_digests(pi) == set()
