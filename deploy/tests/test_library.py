"""setup.sh's shared functions without Docker: provenance classification and retries, the
bad-digest list, the apt key check, the healthchecks.io prompts and the deploy lock."""

from __future__ import annotations

import os
import pty
import re
import stat
import subprocess
import time
from pathlib import Path

import pytest

from conftest import (
    COSIGN_DEFINITE_ERROR,
    COSIGN_NETWORK_ERROR,
    COSIGN_UNSIGNED_ERROR,
    DEPLOY,
    SETUP,
    lib,
    run,
)

DIGEST = "sha256:" + "d" * 64


# --- Provenance: only a definite verification failure blacklists a digest --------------------

# Messages as cosign v3 prints them (pkg/cosign/verify.go, cmd/cosign/cli/verify).
DEFINITE = [
    COSIGN_DEFINITE_ERROR,
    "no matching attestations: none of the expected identities matched what was in the "
    "certificate, got subjects [https://github.com/evil/fork/.github/workflows/build-image.yml"
    "@refs/heads/main] with issuer https://token.actions.githubusercontent.com",
    "no matching attestations: failed to verify certificate identity: no matching "
    "CertificateIdentity found, last error: expected issuer value to match "
    '"https://token.actions.githubusercontent.com", got "https://accounts.google.com"',
    "no valid bundles exist in registry",
    "no matching attestations: x509: certificate has expired or is not yet valid",
    "no matching signatures: invalid signature when validating ASN.1 encoded signature",
    "no signatures found",
    "expected GitHub Workflow Ref not found in certificate",
]
# No attestation at all: refused, but not blacklisted (a release may still be signing).
UNSIGNED = [COSIGN_UNSIGNED_ERROR, "no matching attestations:", "no matching attestations"]
TRANSIENT = [
    COSIGN_NETWORK_ERROR,
    "GET https://ghcr.io/v2/bublemann/mealmate/referrers/sha256:abc: unexpected status code 503 "
    "Service Unavailable",
    "GET https://ghcr.io/token?scope=repository: UNAUTHORIZED: authentication required",
    "TOOMANYREQUESTS: retry later",
    # A verification message that is really a network error (Rekor lookup) is not definite.
    'no matching attestations: Post "https://rekor.sigstore.dev/api/v1/log/entries/retrieve": '
    "dial tcp 1.2.3.4:443: connect: connection refused",
    "updating local metadata and targets: error updating to TUF remote mirror: invalid key",
    "something nobody expected",
]


@pytest.mark.parametrize(
    ("message", "kind"),
    [(m, "definite") for m in DEFINITE]
    + [(m, "unsigned") for m in UNSIGNED]
    + [(m, "transient") for m in TRANSIENT],
)
def test_cosign_failures_are_classified(message: str, kind: str) -> None:
    text = f"Error: {message}\nerror during command execution: {message}\n"
    result = subprocess.run(
        ["bash", "-c", f'source "{SETUP}"; mm_init test; mm_cosign_failure_kind'],
        input=text,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == kind


def verify(shims: Path, tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess, int]:
    calls = tmp_path / "calls.log"
    result = lib(
        f'status=0; mm_verify_provenance {DIGEST} || status=$?; echo "status=$status"',
        env={
            "COSIGN": str(shims / "cosign"),
            "MEALMATE_COSIGN_RETRY_DELAY": "0",
            "MM_TEST_CALLS": str(calls),
            "MM_TEST_COUNTER": str(tmp_path / "counter"),
            **env,
        },
    )
    attempts = sum(1 for line in calls.read_text().splitlines() if "verify-attestation" in line)
    return result, attempts


def test_a_definite_failure_is_not_retried(shims: Path, tmp_path: Path) -> None:
    identity = DEFINITE[1]
    result, attempts = verify(shims, tmp_path, MM_TEST_COSIGN="fail", MM_TEST_COSIGN_ERROR=identity)
    assert result.stdout.strip() == "status=1"
    assert attempts == 1
    assert f"cosign: Error: {identity}" in result.stderr, "cosign's stderr is logged"


def test_no_attestation_yet_is_reported_as_unsigned_without_retries(
    shims: Path, tmp_path: Path
) -> None:
    result, attempts = verify(
        shims, tmp_path, MM_TEST_COSIGN="fail", MM_TEST_COSIGN_ERROR=COSIGN_UNSIGNED_ERROR
    )
    assert result.stdout.strip() == "status=3"
    assert attempts == 1
    assert "no build provenance yet (a release may still be signing)" in result.stderr
    assert "provenance is invalid" not in result.stderr


def test_a_network_failure_is_retried_then_reported_as_unknown(shims: Path, tmp_path: Path) -> None:
    result, attempts = verify(
        shims, tmp_path, MM_TEST_COSIGN="fail", MM_TEST_COSIGN_ERROR=COSIGN_NETWORK_ERROR
    )
    assert result.stdout.strip() == "status=2"
    assert attempts == 3
    assert f"cosign: Error: {COSIGN_NETWORK_ERROR}" in result.stderr
    assert "trying again" in result.stderr


def test_a_network_failure_that_goes_away_verifies(shims: Path, tmp_path: Path) -> None:
    result, attempts = verify(shims, tmp_path, MM_TEST_COSIGN="flaky")
    assert result.stdout.strip() == "status=0"
    assert attempts == 3


# --- state/bad-digest ------------------------------------------------------------------------


@pytest.mark.root
def test_bad_digest_list_keeps_the_last_twenty(tmp_path: Path) -> None:
    (tmp_path / "state").mkdir()
    digests = [f"sha256:{i:064x}" for i in range(25)]
    env = {"MEALMATE_ROOT": str(tmp_path)}
    lib("; ".join(f"mm_record_bad_digest {d}" for d in digests), env=env)
    bad = tmp_path / "state" / "bad-digest"
    assert bad.read_text().split() == digests[5:]
    lib(f"mm_record_bad_digest {digests[10]}", env=env)
    assert bad.read_text().split() == [*digests[5:10], *digests[11:], digests[10]]
    lib(f"mm_unrecord_bad_digest {digests[10]}", env=env)
    assert digests[10] not in bad.read_text().split()
    assert lib(f"mm_is_bad_digest {digests[10]}", env=env, check=False).returncode == 1
    assert lib(f"mm_is_bad_digest {digests[20]}", env=env, check=False).returncode == 0
    assert stat.S_IMODE(bad.stat().st_mode) == 0o644


# --- The apt repository keys ------------------------------------------------------------------


@pytest.fixture(scope="module")
def keys(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str | Path]:
    """Two throw-away keys: A with an encryption subkey, B without."""
    home = tmp_path_factory.mktemp("gnupg")
    home.chmod(0o700)
    env = {**os.environ, "GNUPGHOME": str(home)}
    gpg = ["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", ""]
    fprs = {}
    for name in ("a", "b"):
        run([*gpg, "--quick-gen-key", f"{name} <{name}@example.org>", "ed25519", "sign", "0"],
            env=env)  # fmt: skip
        out = run(["gpg", "--batch", "--with-colons", "--list-keys", f"{name}@example.org"],
                  env=env).stdout  # fmt: skip
        fprs[name] = re.search(r"^fpr:+([0-9A-F]{40}):", out, re.M).group(1)
    run([*gpg, "--quick-add-key", fprs["a"], "cv25519", "encr", "0"], env=env)
    out = run(["gpg", "--batch", "--with-colons", "--list-keys", fprs["a"]], env=env).stdout
    sub = re.findall(r"^fpr:+([0-9A-F]{40}):", out, re.M)[1]
    one, both = home / "one.asc", home / "both.asc"
    one.write_text(run(["gpg", "--armor", "--export", fprs["a"]], env=env).stdout)
    both.write_text(run(["gpg", "--armor", "--export", fprs["a"], fprs["b"]], env=env).stdout)
    return {"a": fprs["a"], "b": fprs["b"], "sub": sub, "one": one, "both": both}


def test_apt_key_needs_exactly_one_primary_key_with_that_fingerprint(keys: dict) -> None:
    def ok(file: Path, fpr: str) -> bool:
        return lib(f"mm_key_has_fpr '{file}' {fpr}", check=False).returncode == 0

    assert ok(keys["one"], keys["a"])
    assert not ok(keys["one"], keys["b"])
    assert not ok(keys["one"], keys["sub"]), "a subkey's fingerprint is not the key's"
    assert not ok(keys["both"], keys["a"]), "a second primary key in the file is refused"
    assert not ok(keys["both"], keys["b"])


# --- healthchecks.io URLs ---------------------------------------------------------------------


@pytest.mark.root
def test_an_invalid_hc_url_never_ends_up_empty_in_env(tmp_path: Path, shims: Path) -> None:
    (tmp_path / "state").mkdir()
    env = {
        "MEALMATE_ROOT": str(tmp_path),
        "TAILSCALE": str(shims / "tailscale"),
        "HC_BACKUP_URL": "hc-ping.com/abc",
    }
    result = lib("mm_write_new_env 2.0-pre", env=env, check=False)
    assert result.returncode != 0
    assert "HC_BACKUP_URL must be an http(s) URL" in result.stderr
    assert not (tmp_path / ".env").exists()

    # A re-run that adds a missing key to an existing .env: the same.
    (tmp_path / ".env").write_text("IMAGE_TAG=2.0-pre\n")
    result = lib("mm_step_env ''", env=env, check=False)
    assert result.returncode != 0
    assert "HC_BACKUP_URL" not in (tmp_path / ".env").read_text()


def test_an_invalid_hc_url_is_asked_for_again_on_a_terminal() -> None:
    controller, terminal = pty.openpty()
    try:
        process = subprocess.Popen(
            ["bash", "-c", f'source "{SETUP}"; mm_init test; mm_ask_hc_url HC_DISK_URL disk'],
            stdin=terminal,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={k: v for k, v in os.environ.items() if not k.startswith("HC_")},
        )
        os.write(controller, b"hc-ping.com/typo\nhttps://hc-ping.com/fixed\n")
        out, err = process.communicate(timeout=30)
    finally:
        os.close(terminal)
        os.close(controller)
    assert process.returncode == 0, err
    assert out == "https://hc-ping.com/fixed"
    assert "'hc-ping.com/typo' is not an http(s) URL; try again" in err


# --- One deploy lock --------------------------------------------------------------------------


@pytest.mark.root
def test_the_deploy_lock_serialises_update_setup_and_rotation(tmp_path: Path) -> None:
    root = tmp_path / "srv"
    (root / "state").mkdir(parents=True)
    (root / ".env").write_text("MEALMATE_SECRET_KEY=old\nIMAGE_TAG=2.0-pre\n")
    env = {
        **os.environ,
        "MEALMATE_ROOT": str(root),
        "MEALMATE_LOCK_WAIT": "1",
        "DOCKER": "false",
        "TAILSCALE": "false",
    }
    lock = root / "state" / "deploy.lock"
    holder = subprocess.Popen(["flock", str(lock), "sleep", "60"])
    try:
        deadline = time.monotonic() + 10
        while run(["flock", "-n", lock, "true"], check=False).returncode == 0:
            assert time.monotonic() < deadline
            time.sleep(0.1)

        update = run(["bash", DEPLOY / "pi" / "bin" / "update.sh"], env=env)
        assert "already running (state/deploy.lock)" in update.stderr

        rotate = run(["bash", SETUP, "--rotate-secret"], env=env, check=False)
        assert rotate.returncode == 1 and "state/deploy.lock" in rotate.stderr
        assert (root / ".env").read_text().startswith("MEALMATE_SECRET_KEY=old\n")

        setup = run(["bash", SETUP, "--skip-system", "--version", "2.0-pre"], env=env, check=False)
        assert setup.returncode == 1 and "state/deploy.lock" in setup.stderr
        assert "step 5" not in setup.stderr, "nothing ran before the lock"

        beat = run(["bash", DEPLOY / "pi" / "bin" / "heartbeat.sh"], env=env)
        assert "skipping this heartbeat" in beat.stderr
    finally:
        holder.kill()
        holder.wait()
