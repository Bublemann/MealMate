"""The Mac's install-backup-pull.sh (OPS-03, plan § 11.3), run to the end with bash 3.2.

Homebrew, ssh, launchctl, tailscale, fdesetup and plutil are shims that log their calls, and
uname says Darwin; ssh-keygen is the real one. The real ssh to the Pi, rrsync and launchd are
checked on the owner's Mac (docs/operations.md § 13.5 item 8).
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

import pytest

from conftest import DEPLOY, run

INSTALL = DEPLOY / "mac" / "install-backup-pull.sh"
HOST = "mealmate.example.ts.net"
PI = f"owner@{HOST}"
HOST_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeHostKeyOfThePi root@mealmate"
HC_URL = "https://hc-ping.com/00000000-0000-0000-0000-000000000000"
RSYNC_VERSION = "rsync  version 3.5.1  protocol version 33"

# More than a pipe buffer (64 KiB) after the line that matters, so a reader that stops early
# always breaks the pipe, as `head -n 1` did with the real rsync on the owner's Mac.
LONG_TAIL = """i=0
while [ "$i" -lt 2000 ]; do
  printf '%080d\\n' 0
  i=$((i + 1))
done
"""

MAC_SHIMS = {
    "uname": "echo Darwin\n",
    "brew": 'if [ "$1" = --prefix ]; then echo "$MM_TEST_PREFIX"; fi\n',
    # Reads the Pi's host key; the other call (sudo setup.sh --set-backup-key) is only logged.
    "ssh": 'case "$*" in *ssh_host_ed25519_key.pub) echo "$MM_TEST_HOST_KEY" ;; esac\n',
    "launchctl": "",
    "tailscale": "",
    "fdesetup": 'echo "FileVault is ${MM_TEST_FILEVAULT:-On}."\n' + LONG_TAIL,
    "plutil": "",
}


def write_tool(path: Path, body: str) -> None:
    path.write_text(f'#!/bin/sh\necho "{path.name} $*" >>"${{MM_TEST_CALLS:-/dev/null}}"\n{body}')
    path.chmod(0o755)


class Mac:
    """A home directory, a Homebrew prefix and the shims the installer runs with."""

    def __init__(self, base: Path, bash: str) -> None:
        self.bash = bash
        self.home, self.prefix, self.calls = base / "home", base / "homebrew", base / "calls"
        shims = base / "shims"
        for directory in (self.home, shims, self.prefix / "bin"):
            directory.mkdir(parents=True)
        for name, body in MAC_SHIMS.items():
            write_tool(shims / name, body)
        write_tool(self.prefix / "bin" / "rsync", f"echo '{RSYNC_VERSION}'\n{LONG_TAIL}")
        write_tool(self.prefix / "bin" / "python3", "")
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "PATH": f"{shims}:{os.environ['PATH']}",
            "BREW": str(shims / "brew"),
            "SSH": str(shims / "ssh"),
            "LAUNCHCTL": str(shims / "launchctl"),
            "TAILSCALE": str(shims / "tailscale"),
            "MM_TEST_PREFIX": str(self.prefix),
            "MM_TEST_HOST_KEY": HOST_KEY,
            "MM_TEST_CALLS": str(self.calls),
        }
        self.app = self.home / ".mealmate-backup"
        self.key = self.home / ".ssh" / "id_ed25519_mealmate_backup"
        self.agent = self.home / "Library" / "LaunchAgents" / "de.mealmate.backup-pull.plist"

    def install(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return run([self.bash, INSTALL, "--pi", PI, *args], env={**self.env, **env})

    def config(self) -> dict[str, str]:
        lines = (self.app / "config").read_text().splitlines()
        return dict(line.split("=", 1) for line in lines if not line.startswith("#"))

    def log(self) -> list[str]:
        return self.calls.read_text().splitlines()


@pytest.fixture
def mac(tmp_path: Path, mac_bash: str) -> Mac:
    return Mac(tmp_path, mac_bash)


def test_installs_scripts_key_config_and_agent(mac: Mac) -> None:
    result = mac.install("--hc-url", HC_URL)

    assert RSYNC_VERSION in result.stdout.splitlines()
    assert "installed; the first pull runs now" in result.stdout
    # FileVault is on (fdesetup's long output too) and shields-up worked.
    assert "WARNING" not in result.stderr
    assert (mac.app / "bin" / "pull.sh").read_bytes() == (DEPLOY / "mac" / "pull.sh").read_bytes()
    prune = (DEPLOY / "common" / "prune.py").read_bytes()
    assert (mac.app / "bin" / "prune.py").read_bytes() == prune
    assert (mac.app / "known_hosts").read_text() == f"{HOST} {' '.join(HOST_KEY.split()[:2])}\n"
    config = mac.config()
    assert config["MM_REMOTE"] == f"mmbackup@{HOST}:"
    assert config["MM_RSYNC"] == f"{mac.prefix}/bin/rsync"
    assert config["HC_MACPULL_URL"] == HC_URL
    assert plistlib.loads(mac.agent.read_bytes())["ProgramArguments"] == [
        "/bin/bash",
        f"{mac.app}/bin/pull.sh",
    ]
    assert (mac.home / "MealMateBackups").is_dir()

    key_type, key_value, _ = mac.key.with_suffix(".pub").read_text().split()
    log = mac.log()
    setup = f"ssh -t {PI} sudo /srv/mealmate/bin/setup.sh --set-backup-key {key_type} {key_value}"
    assert setup in log
    assert "tailscale set --shields-up" in log
    assert f"launchctl bootstrap gui/{os.getuid()} {mac.agent}" in log


def test_a_rerun_keeps_the_key_and_the_ping_url(mac: Mac) -> None:
    mac.install("--hc-url", HC_URL)
    key = mac.key.read_text()

    mac.install()

    assert mac.key.read_text() == key
    assert mac.config()["HC_MACPULL_URL"] == HC_URL
    assert mac.log().count(f"launchctl bootstrap gui/{os.getuid()} {mac.agent}") == 2


def test_warns_when_filevault_is_off(mac: Mac) -> None:
    result = mac.install("--hc-url", HC_URL, MM_TEST_FILEVAULT="Off")

    assert "WARNING: FileVault is off" in result.stderr
    assert "installed; the first pull runs now" in result.stdout
