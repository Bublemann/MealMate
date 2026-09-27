"""setup.sh as a library and its host-file modes; compose file; units; Mac script portability."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
from pathlib import Path

import pytest

from conftest import DEPLOY, SETUP, lib, run

UNITS = sorted(p.name for p in (DEPLOY / "pi" / "systemd").iterdir())


@pytest.mark.parametrize(
    ("version", "tag"),
    [
        ("2.0.0", "2.0"),
        ("v2.0.3", "2.0"),
        ("2.0.0-alpha.1", "2.0-pre"),
        ("2.1.0-rc.2", "2.1-pre"),
        ("2.0-pre", "2.0-pre"),
        ("2.1", "2.1"),
    ],
)
def test_version_selects_the_version_line(version: str, tag: str) -> None:
    assert lib(f"mm_tag_for_version {version}").stdout == tag


@pytest.mark.parametrize("version", ["latest", "2", "2.0.0.1", "2.0-beta", "../2.0"])
def test_bad_versions_are_refused(version: str) -> None:
    assert lib(f"mm_tag_for_version '{version}'", check=False).returncode != 0


def test_sourcing_runs_nothing(tmp_path: Path) -> None:
    result = lib("echo sourced", env={"MEALMATE_ROOT": str(tmp_path / "none")})
    assert result.stdout.strip() == "sourced"
    assert not (tmp_path / "none").exists()


@pytest.mark.root
def test_new_env_file(tmp_path: Path, shims: Path) -> None:
    """Random secret, the Tailscale HTTPS address, the version line, HC URLs; 0600 root."""
    (tmp_path / "state").mkdir()
    env = {
        "MEALMATE_ROOT": str(tmp_path),
        "TAILSCALE": str(shims / "tailscale"),
        "MM_TEST_TS_DNS": "mealmate.tail1234.ts.net.",
        "HC_BACKUP_URL": "https://hc-ping.com/abc",
    }
    lib("mm_write_new_env 2.0-pre", env=env)
    lib("mm_write_new_env 2.0-pre", env=env)
    env_file = tmp_path / ".env"
    values = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line)
    assert re.fullmatch(r"[0-9a-f]{64}", values["MEALMATE_SECRET_KEY"])
    assert values["MEALMATE_PUBLIC_URL"] == "https://mealmate.tail1234.ts.net"
    assert values["IMAGE_TAG"] == "2.0-pre"
    assert values["HC_BACKUP_URL"] == "https://hc-ping.com/abc"
    assert values["HC_HEARTBEAT_URL"] == values["HC_DISK_URL"] == values["HC_UPDATE_URL"] == ""
    info = env_file.stat()
    assert stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == 0
    assert not list(tmp_path.glob(".mm-tmp.*"))


@pytest.mark.root
def test_update_host_files_installs_everything_atomically(tmp_path: Path, shims: Path) -> None:
    root, units = tmp_path / "srv", tmp_path / "systemd"
    units.mkdir()
    (units / "mealmate-retired.timer").write_text("[Timer]\n")
    (units / "other.timer").write_text("[Timer]\n")
    calls = tmp_path / "calls.log"
    env = {
        **os.environ,
        "MEALMATE_ROOT": str(root),
        "MEALMATE_SYSTEMD_DIR": str(units),
        "SYSTEMCTL": str(shims / "systemctl"),
        "MM_TEST_CALLS": str(calls),
    }
    run(["bash", SETUP, "--update-host-files", "--from", DEPLOY], env=env)
    # Running it again replaces the files (new inodes: a running script keeps its old one).
    inode = (root / "bin" / "update.sh").stat().st_ino
    run(["bash", SETUP, "--update-host-files", "--from", DEPLOY], env=env)
    assert (root / "bin" / "update.sh").stat().st_ino != inode

    for script in ("mm-compose", "backup.sh", "update.sh", "heartbeat.sh", "disk-check.sh",
                   "setup.sh", "prune.py"):  # fmt: skip
        path = root / "bin" / script
        assert stat.S_IMODE(path.stat().st_mode) == 0o755, script
    assert (root / "compose.yml").read_bytes() == (DEPLOY / "compose.yml").read_bytes()
    assert (root / "bin" / "setup.sh").read_bytes() == SETUP.read_bytes()
    assert sorted(p.name for p in units.iterdir()) == sorted([*UNITS, "other.timer"])
    backup_service = (units / "mealmate-backup.service").read_text()
    assert f"ExecStart={root}/bin/backup.sh" in backup_service
    assert "/srv/mealmate" not in backup_service
    assert not list(root.rglob(".mm-*")) and not list(units.glob(".mm-*"))

    log = calls.read_text().splitlines()
    assert "systemctl disable --now mealmate-retired.timer" in log
    assert "systemctl daemon-reload" in log
    enabled = [line for line in log if line.startswith("systemctl enable --now")][-1].split()[3:]
    assert sorted(enabled) == sorted(u for u in UNITS if u.endswith((".timer", ".path")))


@pytest.mark.root
def test_set_backup_key_restricts_to_read_only_rrsync(tmp_path: Path, shims: Path) -> None:
    home = tmp_path / "mmbackup"
    (home / ".ssh").mkdir(parents=True)
    env = {
        **os.environ,
        "PATH": f"{shims}:{os.environ['PATH']}",
        "MEALMATE_ROOT": "/srv/mealmate",
        "MEALMATE_BACKUP_USER": "root",
        "MEALMATE_BACKUP_GROUP": "root",
        "MEALMATE_BACKUP_HOME": str(home),
    }
    key = "AAAAC3NzaC1lZDI1NTE5AAAAIC2l1Pv3m3sR1Ukn8mHkCZ0wX8q3QYxY4N7d0w7sWm1k"
    run(["bash", SETUP, "--set-backup-key", "ssh-ed25519", key], env=env)
    line = (home / ".ssh" / "authorized_keys").read_text()
    assert line == (
        f'restrict,command="{shims}/rrsync -ro /srv/mealmate/backups" '
        f"ssh-ed25519 {key} mealmate-backup-pull\n"
    )
    assert stat.S_IMODE((home / ".ssh" / "authorized_keys").stat().st_mode) == 0o600
    for bad in (["ssh-rsa", key], ["ssh-ed25519", 'x" command="sh']):
        assert run(["bash", SETUP, "--set-backup-key", *bad], env=env, check=False).returncode


def test_units_pass_systemd_analyze(tmp_path: Path) -> None:
    analyze = shutil.which("systemd-analyze")
    system_units = Path("/usr/lib/systemd/system")
    if not analyze or not system_units.is_dir():
        pytest.skip("systemd-analyze is not available")
    root = tmp_path / "root"
    shutil.copytree(system_units, root / "usr/lib/systemd/system", symlinks=True)
    (root / "etc/systemd/system").mkdir(parents=True)
    (root / "bin").mkdir()
    shutil.copy(shutil.which("sh") or "/bin/sh", root / "bin/sh")
    (root / "srv/mealmate/bin").mkdir(parents=True)
    for script in ("backup.sh", "update.sh", "heartbeat.sh", "disk-check.sh", "mm-compose"):
        (root / "srv/mealmate/bin" / script).write_text("#!/bin/sh\n")
        (root / "srv/mealmate/bin" / script).chmod(0o755)
    for unit in UNITS:
        shutil.copy(DEPLOY / "pi/systemd" / unit, root / "etc/systemd/system" / unit)
    result = run(
        [analyze, "verify", "--man=no", f"--root={root}",
         *(str(root / "etc/systemd/system" / u) for u in UNITS)],
        check=False,
    )  # fmt: skip
    assert result.returncode == 0 and not result.stderr.strip(), result.stderr


def test_unit_schedules_match_the_plan() -> None:
    def value(unit: str, key: str) -> list[str]:
        text = (DEPLOY / "pi/systemd" / unit).read_text()
        return re.findall(rf"^{key}=(.*)$", text, re.MULTILINE)

    assert value("mealmate-backup.timer", "OnCalendar") == ["*-*-* 00,06,12,18:15:00"]
    assert value("mealmate-backup.path", "PathExists") == [
        "/srv/mealmate/data/status/backup-request"
    ]
    assert value("mealmate-backup-manual.service", "ExecStart") == [
        "/srv/mealmate/bin/backup.sh --label manual"
    ]
    assert value("mealmate-update.timer", "OnCalendar") == ["*-*-* 04:30:00"]
    assert value("mealmate-heartbeat.timer", "OnUnitActiveSec") == ["5min"]
    assert value("mealmate-disk.timer", "OnCalendar") == ["hourly"]
    assert value("mealmate-off-refresh.timer", "OnCalendar") == ["*-*-* 03:00:00"]
    assert value("mealmate-cleanup.timer", "OnCalendar") == ["*-*-* 03:30:00"]
    assert value("mealmate-restore-test.service", "ExecStart") == [
        "/srv/mealmate/bin/backup.sh --verify-latest"
    ]


def test_compose_file_is_the_hardened_production_file() -> None:
    """docker compose config with the example environment (plan § 11.1)."""
    if not shutil.which("docker"):
        pytest.skip("docker CLI is not available")
    result = run(
        ["docker", "compose", "-f", DEPLOY / "compose.yml", "--env-file",
         DEPLOY / "pi/env.example", "config", "--format", "json"],
        env={k: v for k, v in os.environ.items() if not k.startswith(("IMAGE_", "COMPOSE_"))},
    )  # fmt: skip
    app = json.loads(result.stdout)["services"]["app"]
    assert app["image"] == "ghcr.io/bublemann/mealmate:2.0-pre"
    assert app["network_mode"] == "host"
    assert app["environment"]["UVICORN_HOST"] == "127.0.0.1"
    assert set(app["environment"]) == {
        "MEALMATE_SECRET_KEY",
        "MEALMATE_PUBLIC_URL",
        "MEALMATE_IMAGE_DIGEST",
        "UVICORN_HOST",
    }, "the HC_* URLs and IMAGE_TAG must never reach the container"
    assert app["environment"]["MEALMATE_IMAGE_DIGEST"] == "", "unpinned: no digest"
    assert app["user"] == "10001:10001"
    assert app["read_only"] is True
    assert app["cap_drop"] == ["ALL"]
    assert app["security_opt"] == ["no-new-privileges:true"]
    assert app["pids_limit"] == 200
    mounts = {(v["target"], v.get("read_only", False)) for v in app["volumes"]}
    assert mounts == {("/data", False), ("/status", True)}
    assert app["logging"]["options"] == {"max-size": "10m", "max-file": "3"}

    pinned = run(
        ["docker", "compose", "-f", DEPLOY / "compose.yml", "--env-file",
         DEPLOY / "pi/env.example", "config", "--format", "json"],
        env={**os.environ, "IMAGE_REF": "ghcr.io/bublemann/mealmate@sha256:" + "a" * 64},
    )  # fmt: skip
    pinned_app = json.loads(pinned.stdout)["services"]["app"]
    assert pinned_app["image"].endswith("@sha256:" + "a" * 64)
    # The admin page shows the pinned digest (the app keeps the part after "@").
    assert pinned_app["environment"]["MEALMATE_IMAGE_DIGEST"] == pinned_app["image"]

    # Everything else is exactly plan § 11.1 (plus the digest line above).
    plan = (DEPLOY.parent / "docs" / "plan.md").read_text(encoding="utf-8")
    block = re.search(r"`compose.yml` \(single service `app`\):\n\n```yaml\n(.*?)```", plan, re.S)
    assert block, "plan § 11.1 has the compose block"
    ours = [
        line
        for line in (DEPLOY / "compose.yml").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    extra = "      MEALMATE_IMAGE_DIGEST: ${IMAGE_REF:-}"
    assert extra in ours
    assert [line for line in ours if line != extra] == block.group(1).rstrip("\n").splitlines()


BASH4_ONLY = [
    (r"\bmapfile\b|\breadarray\b", "mapfile/readarray"),
    (r"\bdeclare\s+-[a-zA-Z]*[An]", "associative arrays / namerefs"),
    (r"\blocal\s+-n\b", "namerefs"),
    (r"\$\{[^}]*(,,|\^\^)[^}]*\}", "case modification"),
    (r"\|&", "|&"),
    (r"&>>", "&>>"),
    (r";;&|;&", "fall-through case"),
    (r"\bcoproc\b", "coproc"),
    (r"\[\[\s+-v\b", "[[ -v"),
    (r"\$EPOCH(SECONDS|REALTIME)", "EPOCHSECONDS"),
    (r"\{[a-zA-Z_]+\}[<>]", "automatic file descriptors"),
    (r"\bwait\s+-n\b", "wait -n"),
    (r"\$\{[A-Za-z_]+\[-1\]\}", "negative array index"),
    (r"\bshopt\s+-s\s+(globstar|lastpipe)", "globstar/lastpipe"),
]


@pytest.mark.parametrize("script", ["pull.sh", "install-backup-pull.sh"])
def test_mac_scripts_avoid_bash4_features(script: str) -> None:
    """macOS ships bash 3.2 (the pull tests also run pull.sh with a real bash 3.2)."""
    text = (DEPLOY / "mac" / script).read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for pattern, feature in BASH4_ONLY:
        assert not re.search(pattern, code), f"{script} uses {feature}"
    assert text.startswith("#!/bin/bash\n")


def test_mac_scripts_parse_with_bash32(mac_bash: str) -> None:
    for script in ("pull.sh", "install-backup-pull.sh"):
        run([mac_bash, "-n", DEPLOY / "mac" / script])


def test_launchd_plist() -> None:
    import plistlib

    raw = (DEPLOY / "mac" / "de.mealmate.backup-pull.plist").read_bytes()
    plist = plistlib.loads(raw.replace(b"__HOME__", b"/Users/owner"))
    assert plist["Label"] == "de.mealmate.backup-pull"
    assert plist["StartInterval"] == 3600
    assert plist["RunAtLoad"] is True
    assert plist["ProgramArguments"] == ["/bin/bash", "/Users/owner/.mealmate-backup/bin/pull.sh"]
