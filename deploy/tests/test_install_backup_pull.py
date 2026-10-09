"""The Mac's install-backup-pull.sh (OPS-03, plan § 11.3), run to the end with bash 3.2.

Homebrew, ssh, launchctl, tailscale, fdesetup and plutil are shims that log their calls, and
uname says Darwin; ssh-keygen is the real one. The real ssh to the Pi, rrsync and launchd are
checked on the owner's Mac (docs/operations.md § 13.5 item 8).
"""

from __future__ import annotations

import os
import plistlib
from pathlib import Path

from conftest import DEPLOY, run

INSTALL = DEPLOY / "mac" / "install-backup-pull.sh"
HOST = "mealmate.example.ts.net"
PI = f"owner@{HOST}"
HOST_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFakeHostKeyOfThePi root@mealmate"
HC_URL = "https://hc-ping.com/00000000-0000-0000-0000-000000000000"
RSYNC_VERSION = "rsync  version 3.5.1  protocol version 33"

SHIMS = {
    "uname": "echo Darwin\n",
    "brew": 'if [ "$1" = --prefix ]; then echo "$MM_TEST_PREFIX"; fi\n',
    # Reads the Pi's host key; the other call (sudo setup.sh --set-backup-key) is only logged.
    "ssh": 'case "$*" in *ssh_host_ed25519_key.pub) echo "$MM_TEST_HOST_KEY" ;; esac\n',
    "launchctl": "",
    "tailscale": "",
    "fdesetup": "echo 'FileVault is On.'\n",
    "plutil": "",
}

# Real rsync prints about 25 lines after the first, in several writes. Writing more than a pipe
# buffer (64 KiB) makes sure a reader that stops after the first line breaks the pipe, as it did
# on the owner's Mac.
RSYNC = f"""echo '{RSYNC_VERSION}'
i=0
while [ "$i" -lt 2000 ]; do
  echo 'Capabilities: 64-bit files, 64-bit inums, 64-bit timestamps, 64-bit long ints,'
  i=$((i + 1))
done
"""


def write_tool(path: Path, body: str) -> None:
    path.write_text(f'#!/bin/sh\necho "{path.name} $*" >>"$MM_TEST_CALLS"\n{body}')
    path.chmod(0o755)


def test_installs_scripts_key_config_and_agent(tmp_path: Path, mac_bash: str) -> None:
    home, shims, prefix = tmp_path / "home", tmp_path / "shims", tmp_path / "homebrew"
    for directory in (home, shims, prefix / "bin"):
        directory.mkdir(parents=True)
    for name, body in SHIMS.items():
        write_tool(shims / name, body)
    write_tool(prefix / "bin" / "rsync", RSYNC)
    write_tool(prefix / "bin" / "python3", "")
    calls = tmp_path / "calls"
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{shims}:{os.environ['PATH']}",
        "BREW": str(shims / "brew"),
        "SSH": str(shims / "ssh"),
        "LAUNCHCTL": str(shims / "launchctl"),
        "TAILSCALE": str(shims / "tailscale"),
        "MM_TEST_PREFIX": str(prefix),
        "MM_TEST_HOST_KEY": HOST_KEY,
        "MM_TEST_CALLS": str(calls),
    }

    result = run([mac_bash, INSTALL, "--pi", PI, "--hc-url", HC_URL], env=env)

    assert RSYNC_VERSION in result.stdout.splitlines()
    assert "installed; the first pull runs now" in result.stdout
    assert "WARNING" not in result.stderr  # FileVault is on, shields-up worked
    app = home / ".mealmate-backup"
    assert (app / "bin" / "pull.sh").read_bytes() == (DEPLOY / "mac" / "pull.sh").read_bytes()
    assert (app / "bin" / "prune.py").read_bytes() == (DEPLOY / "common" / "prune.py").read_bytes()
    assert (app / "known_hosts").read_text() == f"{HOST} {' '.join(HOST_KEY.split()[:2])}\n"
    config = dict(
        line.split("=", 1)
        for line in (app / "config").read_text().splitlines()
        if not line.startswith("#")
    )
    assert config["MM_REMOTE"] == f"mmbackup@{HOST}:"
    assert config["MM_RSYNC"] == f"{prefix}/bin/rsync"
    assert config["HC_MACPULL_URL"] == HC_URL
    agent = home / "Library" / "LaunchAgents" / "de.mealmate.backup-pull.plist"
    assert plistlib.loads(agent.read_bytes())["ProgramArguments"] == [
        "/bin/bash",
        f"{app}/bin/pull.sh",
    ]
    assert (home / "MealMateBackups").is_dir()

    key_type, key_value, _ = (home / ".ssh" / "id_ed25519_mealmate_backup.pub").read_text().split()
    log = calls.read_text().splitlines()
    setup = f"ssh -t {PI} sudo /srv/mealmate/bin/setup.sh --set-backup-key {key_type} {key_value}"
    assert setup in log
    assert "tailscale set --shields-up" in log
    assert f"launchctl bootstrap gui/{os.getuid()} {agent}" in log
