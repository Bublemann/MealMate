"""Fixtures for the deploy tests (plan § 9, "Deploy" row).

The host scripts run for real against the production image, a local ``registry:2`` and a
throw-away installation root (``MEALMATE_ROOT``). Only what cannot run here is faked, through the
scripts' own tool overrides: ``cosign`` (no signed images in a local registry), ``tailscale``
and ``systemctl`` (shims that log their calls), and healthchecks.io (a local HTTP server that
records the pings). See docs/operations.md, "Test overrides".

Environment:
- ``MEALMATE_TEST_IMAGE``: the production image to test (default ``mealmate-ops:base``). The
  suite derives ``<prefix>:good`` from it with the current ``deploy/`` files, so the host files
  that update.sh installs from the image are the ones under test.
- ``MEALMATE_TEST_IMAGE_PREFIX``: repository for the derived images (default ``mealmate-ops``).
- ``MM_TEST_MAC_BASH``: a bash 3.2 to run the Mac scripts with; by default it is extracted from
  the ``bash:3.2`` image (macOS ships bash 3.2).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DEPLOY = REPO / "deploy"
BASE_IMAGE = os.environ.get("MEALMATE_TEST_IMAGE", "mealmate-ops:base")
IMAGE_PREFIX = os.environ.get("MEALMATE_TEST_IMAGE_PREFIX", "mealmate-ops")
REGISTRY_IMAGE = (
    "registry:2@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373"
)
BASH32_IMAGE = "bash:3.2@sha256:0fd7cb8499c63a3c9345e7088a9cd83bb69f6e895e83833859aff838a0312091"
REGISTRY_PORT = 18150
HC_PORT = 18151
APP_UID = 10001
TAG = "2.0-pre"


def run(
    cmd: list[str | Path],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
    timeout: float = 900,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Runs a command without a terminal on stdin; fails with its output if `check`."""
    result = subprocess.run(
        [str(part) for part in cmd],
        env=env,
        input="",
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=cwd,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"{' '.join(map(str, cmd))} exited with {result.returncode}\n"
            f"--- stdout\n{result.stdout}\n--- stderr\n{result.stderr}"
        )
    return result


SETUP = DEPLOY / "pi" / "setup.sh"


def lib(script: str, env: dict[str, str] | None = None, check: bool = True):
    """Runs `script` in bash with setup.sh sourced (library mode: nothing runs by itself)."""
    return run(
        ["bash", "-c", f'set -euo pipefail; source "{SETUP}"; mm_init test; {script}'],
        env={**os.environ, **(env or {})},
        check=check,
    )


def docker_ok() -> bool:
    try:
        return run(["docker", "info"], check=False, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """`root` tests need root (the scripts chown to the app's uid 10001 and to root); `docker`
    tests need root and Docker. CI sets MM_TEST_REQUIRE_ALL=1, so a missing prerequisite fails
    instead of skipping."""
    needs = {m for item in items for m in ("root", "docker") if m in item.keywords}
    reasons = {}
    if needs and os.geteuid() != 0:
        reasons["root"] = reasons["docker"] = "the host scripts must run as root (sudo)"
    elif "docker" in needs and not docker_ok():
        reasons["docker"] = "Docker is not available"
    if not reasons:
        return
    if os.environ.get("MM_TEST_REQUIRE_ALL") == "1":
        raise pytest.UsageError(f"deploy tests cannot run: {', '.join(set(reasons.values()))}")
    for item in items:
        for marker, reason in reasons.items():
            if marker in item.keywords:
                item.add_marker(pytest.mark.skip(reason=reason))


# --- healthchecks.io stand-in -----------------------------------------------------------------


@dataclass(frozen=True)
class Ping:
    path: str
    body: str


class HealthchecksServer:
    """Records every ping; ``url(check)`` is a ping URL, ``<url>/fail`` its failure endpoint."""

    def __init__(self) -> None:
        self.pings: list[Ping] = []
        self._lock = threading.Lock()
        pings, lock = self.pings, self._lock

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8", "replace")
                with lock:
                    pings.append(Ping(self.path, body))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

            do_GET = do_POST

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", HC_PORT), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def url(self, check: str) -> str:
        return f"http://127.0.0.1:{HC_PORT}/{check}"

    def of(self, check: str) -> list[Ping]:
        with self._lock:
            return [p for p in self.pings if p.path in (f"/{check}", f"/{check}/fail")]

    def last(self, check: str) -> Ping:
        pings = self.of(check)
        assert pings, f"no ping for {check}"
        return pings[-1]

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture(scope="session")
def hc() -> Iterator[HealthchecksServer]:
    server = HealthchecksServer()
    yield server
    server.close()


# --- Shims for the tools that need real hardware or accounts ----------------------------------

COSIGN_DEFINITE_ERROR = (
    "none of the attestations matched the predicate type: https://slsa.dev/provenance/v1, "
    "found: https://spdx.dev/Document"
)
COSIGN_NETWORK_ERROR = (
    'getting trusted root: Get "https://tuf-repo-cdn.sigstore.dev/timestamp.json": '
    "dial tcp: lookup tuf-repo-cdn.sigstore.dev: i/o timeout"
)

SHIMS = {
    # MM_TEST_COSIGN: pass | fail (prints MM_TEST_COSIGN_ERROR the way cosign does) | flaky (a
    # network error for the first MM_TEST_COSIGN_FAILURES calls, counted in MM_TEST_COUNTER).
    "cosign": f"""#!/bin/sh
echo "cosign $*" >>"${{MM_TEST_CALLS:-/dev/null}}"
fail() {{
  echo "Error: $1" >&2
  echo "error during command execution: $1" >&2
  exit 1
}}
case "${{MM_TEST_COSIGN:-pass}}" in
  fail) fail "${{MM_TEST_COSIGN_ERROR:-{COSIGN_DEFINITE_ERROR}}}" ;;
  flaky)
    n=$(($(cat "$MM_TEST_COUNTER" 2>/dev/null || echo 0) + 1))
    echo "$n" >"$MM_TEST_COUNTER"
    [ "$n" -gt "${{MM_TEST_COSIGN_FAILURES:-2}}" ] || fail '{COSIGN_NETWORK_ERROR}'
    ;;
esac
echo '{{"payloadType": "application/vnd.in-toto+json"}}'
""",
    # "Installs" the tools a test hid with bind mounts (MM_TEST_HIDDEN) by unmounting them.
    "apt-get": """#!/bin/sh
echo "apt-get $*" >>"${MM_TEST_CALLS:-/dev/null}"
if [ "$1" = install ] || [ "$2" = install ]; then
  for tool in ${MM_TEST_HIDDEN:-}; do umount "$tool"; done
fi
""",
    "tailscale": """#!/bin/sh
echo "tailscale $*" >>"${MM_TEST_CALLS:-/dev/null}"
if [ "$1" = status ]; then
  printf '{"BackendState": "%s", "Self": {"DNSName": "%s", "Tags": ["tag:mealmate"]}}\\n' \\
    "${MM_TEST_TS_STATE:-Running}" "${MM_TEST_TS_DNS:-mealmate.example.ts.net.}"
fi
""",
    "systemctl": """#!/bin/sh
echo "systemctl $*" >>"${MM_TEST_CALLS:-/dev/null}"
""",
    "rrsync": """#!/bin/sh
exit 0
""",
}


@pytest.fixture(scope="session")
def shims(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("shims")
    for name, text in SHIMS.items():
        path = directory / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
    return directory


# --- Images and registry ----------------------------------------------------------------------

BAD_ENTRYPOINT = """#!/bin/sh
# A deliberately broken release for the rollback test: it migrates the database to a revision the
# previous version does not know, changes the sentinel row, adds a table and plants a symlink to
# a host file next to the database. Then it never becomes healthy.
python - <<'EOF'
import os, sqlite3
db = sqlite3.connect("/data/mealmate.db")
db.execute("UPDATE alembic_version SET version_num = 'ffffffffffff'")
db.execute("UPDATE users SET display_name = 'Broken by the bad image' WHERE username = 'admin'")
db.execute("CREATE TABLE bad_image_marker (note TEXT)")
db.execute("INSERT INTO bad_image_marker VALUES ('written by the bad image')")
db.commit()
db.close()
open("/data/bad-image-ran", "w").close()
victim = os.environ.get("MM_TEST_VICTIM")
if victim:
    for name in ("mealmate.db-wal", "mealmate.db-shm", "mealmate.db-journal"):
        path = os.path.join("/data", name)
        if os.path.lexists(path):
            os.remove(path)
        os.symlink(victim, path)
EOF
exec sleep 3600
"""

# A release that answers the health check for a moment, then crashes (and is restarted by
# Docker, and crashes again): healthy once, never stable.
FLAKY_ENTRYPOINT = """#!/bin/sh
exec python - <<'EOF'
import http.server, os, time
class Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')
    def log_message(self, *args):
        pass
port = int(os.environ.get("UVICORN_PORT", "8080"))
server = http.server.HTTPServer(("127.0.0.1", port), Health)
server.timeout = 0.1
end = time.monotonic() + float(os.environ.get("MM_TEST_FLAKY_SECONDS", "2"))
while time.monotonic() < end:
    server.handle_request()
raise SystemExit("crashed on purpose")
EOF
"""


@dataclass(frozen=True)
class Images:
    good: str
    good2: str
    good3: str
    bad: str
    flaky: str


def _build(tag: str, dockerfile: str, context: Path) -> str:
    (context / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    # The default builder (docker driver) sees local images, even where CI switched to buildx.
    build = ["docker", "buildx", "build", "--builder", "default", "--load", "--quiet"]
    run([*build, "--tag", tag, str(context)], timeout=600)
    return tag


@pytest.fixture(scope="session")
def images(tmp_path_factory: pytest.TempPathFactory) -> Images:
    """The image under test with the current deploy/ files, plus variants for updates."""
    if run(["docker", "image", "inspect", BASE_IMAGE], check=False).returncode != 0:
        pytest.fail(
            f"image {BASE_IMAGE} not found; build it (make image) or set MEALMATE_TEST_IMAGE"
        )
    context = tmp_path_factory.mktemp("image-context")
    shutil.copytree(
        DEPLOY, context / "deploy", ignore=shutil.ignore_patterns("tests", "__pycache__")
    )
    (context / "bad-entrypoint").write_text(BAD_ENTRYPOINT, encoding="utf-8")
    (context / "flaky-entrypoint").write_text(FLAKY_ENTRYPOINT, encoding="utf-8")
    good = _build(
        f"{IMAGE_PREFIX}:good",
        f"FROM {BASE_IMAGE}\nCOPY deploy/ /opt/mealmate/deploy/\n"
        "LABEL de.mealmate.test.variant=good\n",
        context,
    )
    variant = "FROM {good}\nLABEL de.mealmate.test.variant={name}\n"
    return Images(
        good=good,
        good2=_build(f"{IMAGE_PREFIX}:good2", variant.format(good=good, name="good2"), context),
        good3=_build(f"{IMAGE_PREFIX}:good3", variant.format(good=good, name="good3"), context),
        bad=_build(
            f"{IMAGE_PREFIX}:bad",
            f"FROM {good}\nCOPY --chmod=0755 bad-entrypoint /usr/local/bin/mealmate-entrypoint\n"
            "LABEL de.mealmate.test.variant=bad\n",
            context,
        ),
        flaky=_build(
            f"{IMAGE_PREFIX}:flaky",
            f"FROM {good}\nCOPY --chmod=0755 flaky-entrypoint /usr/local/bin/mealmate-entrypoint\n"
            "LABEL de.mealmate.test.variant=flaky\n",
            context,
        ),
    )


class Registry:
    host = f"127.0.0.1:{REGISTRY_PORT}"

    def push(self, local: str, repository: str, tag: str = TAG) -> str:
        """Pushes `local` as `repository:tag` and returns the digest the tag now points to."""
        remote = f"{self.host}/{repository}:{tag}"
        run(["docker", "tag", local, remote])
        run(["docker", "push", "--quiet", remote], timeout=600)
        run(["docker", "image", "rm", remote])
        out = run(
            ["docker", "buildx", "imagetools", "inspect", remote, "--format", "{{json .Manifest}}"]
        ).stdout
        return json.loads(out)["digest"]


@pytest.fixture(scope="session")
def registry() -> Iterator[Registry]:
    name = f"mm-ops-registry-{os.getpid()}"
    run(
        ["docker", "run", "--detach", "--rm", "--name", name, "--publish",
         f"127.0.0.1:{REGISTRY_PORT}:5000", REGISTRY_IMAGE],
        timeout=300,
    )  # fmt: skip
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        probe = ["curl", "-fsS", "--noproxy", "*", f"http://{Registry.host}/v2/"]
        if run(probe, check=False).returncode == 0:
            break
        time.sleep(0.5)
    yield Registry()
    run(["docker", "rm", "--force", name], check=False)


# --- A throw-away Pi installation -------------------------------------------------------------


@dataclass
class Pi:
    """An installation root plus everything setup.sh would touch outside of it."""

    name: str
    base: Path
    port: int
    repository: str
    hc: HealthchecksServer
    env: dict[str, str] = field(default_factory=dict)

    @property
    def root(self) -> Path:
        return self.base / "srv"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def state(self) -> Path:
        return self.root / "state"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def image(self) -> str:
        return f"{Registry.host}/{self.repository}"

    def check(self, name: str) -> str:
        return f"{self.name}-{name}"

    def calls(self) -> list[str]:
        path = Path(self.env["MM_TEST_CALLS"])
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def setup(self, *args: str, check: bool = True, **extra: str) -> subprocess.CompletedProcess:
        return run(
            ["bash", DEPLOY / "pi" / "setup.sh", "--skip-system", *args],
            env={**self.env, **extra},
            check=check,
        )

    def script(self, name: str, *args: str, check: bool = True, **extra: str):
        """Runs an installed script from <root>/bin."""
        return run(
            ["bash", self.root / "bin" / name, *args], env={**self.env, **extra}, check=check
        )

    def compose(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return run([DEPLOY / "pi" / "bin" / "mm-compose", *args], env=self.env, check=check)

    def app(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return self.compose("exec", "-T", "app", *args, check=check)

    def query(self, sql: str) -> list[list[object]]:
        """Rows of a read-only query on the live database, run inside the container."""
        code = (
            "import json, sqlite3, sys\n"
            "db = sqlite3.connect('file:/data/mealmate.db?mode=ro', uri=True)\n"
            "print(json.dumps([list(r) for r in db.execute(sys.argv[1])]))\n"
        )
        return json.loads(self.app("python", "-c", code, sql).stdout)

    def counts(self) -> dict[str, int]:
        tables = [
            row[0]
            for row in self.query(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {t: self.query(f'SELECT count(*) FROM "{t}"')[0][0] for t in sorted(tables)}

    def container_image(self) -> str:
        cid = self.compose("ps", "-q", "app").stdout.strip()
        return run(["docker", "inspect", "--format", "{{.Config.Image}}", cid]).stdout.strip()

    def pinned(self) -> str:
        return (self.state / "override.env").read_text(encoding="utf-8").strip()

    def backup_status(self) -> dict:
        return json.loads((self.state / "status" / "backup.json").read_text(encoding="utf-8"))

    def remove_containers(self) -> None:
        ids = run(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={self.name}"],
            check=False,
        ).stdout.split()
        if ids:
            run(["docker", "rm", "--force", "--volumes", *ids], check=False)


def forget_local_images(repository: str) -> None:
    """Drops this host's references to `repository` (left by an earlier run), so a test sees
    only what the scripts pull. The layers stay, shared with the local mealmate-ops images."""
    out = run(
        ["docker", "image", "ls", "--digests", "--format", "{{.Tag}} {{.Digest}}", repository],
        check=False,
    ).stdout
    for tag, digest in (line.split() for line in out.splitlines() if line.strip()):
        ref = f"{repository}@{digest}" if digest != "<none>" else f"{repository}:{tag}"
        run(["docker", "image", "rm", ref], check=False)
        if tag != "<none>":
            run(["docker", "image", "rm", f"{repository}:{tag}"], check=False)


def write_env(pi: Pi) -> None:
    lines = [
        f"MEALMATE_SECRET_KEY={secrets.token_hex(32)}",
        f"MEALMATE_PUBLIC_URL=http://127.0.0.1:{pi.port}",
        f"IMAGE_TAG={TAG}",
        f"HC_HEARTBEAT_URL={pi.hc.url(pi.check('heartbeat'))}",
        f"HC_BACKUP_URL={pi.hc.url(pi.check('backup'))}",
        f"HC_UPDATE_URL={pi.hc.url(pi.check('update'))}",
        f"HC_DISK_URL={pi.hc.url(pi.check('disk'))}",
    ]
    env_file = pi.root / ".env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env_file.chmod(0o600)


@pytest.fixture
def make_pi(
    tmp_path_factory: pytest.TempPathFactory, hc: HealthchecksServer, shims: Path
) -> Iterator:
    """``make_pi(name, port, repository, env_file=True)`` → a fresh card, cleaned up afterwards."""
    created: list[Pi] = []

    def make(name: str, port: int, repository: str, *, env_file: bool = True) -> Pi:
        forget_local_images(f"{Registry.host}/{repository}")
        base = tmp_path_factory.mktemp(name)
        base.chmod(0o755)
        # backup.sh reads data/media as the app user, which must reach it like on the Pi.
        for parent in base.parents:
            if parent == Path(tempfile.gettempdir()):
                break
            parent.chmod(parent.stat().st_mode | 0o011)
        pi = Pi(name=f"mm-ops-{name}", base=base, port=port, repository=repository, hc=hc)
        pi.root.mkdir(mode=0o755)
        ts = base / "tailscale"
        ts.mkdir()
        (ts / "tailscaled.state").write_text(
            json.dumps({"_machinekey": secrets.token_hex(16)}), encoding="utf-8"
        )
        ssh = base / "ssh"
        ssh.mkdir()
        for kind in ("ed25519", "rsa"):
            (ssh / f"ssh_host_{kind}_key").write_text(secrets.token_hex(32), encoding="utf-8")
            (ssh / f"ssh_host_{kind}_key.pub").write_text(f"ssh-{kind} {secrets.token_hex(8)}\n")
        home = base / "mmbackup"
        (home / ".ssh").mkdir(parents=True)
        (home / ".ssh" / "authorized_keys").write_text(
            f'restrict,command="rrsync -ro /srv/mealmate/backups" ssh-ed25519 {name}\n'
        )
        victim = base / "victim"
        victim.write_text("host file that must never be written\n", encoding="utf-8")
        (pi.root / "compose.test.yml").write_text(
            "# Test-only additions: the app's port (host network), fast bcrypt, the victim path.\n"
            "services:\n  app:\n    environment:\n"
            f'      UVICORN_PORT: "{port}"\n'
            '      MEALMATE_BCRYPT_ROUNDS: "4"\n'
            f'      MM_TEST_VICTIM: "{victim}"\n',
            encoding="utf-8",
        )
        pi.env = {
            **os.environ,
            "PATH": f"{shims}:{os.environ['PATH']}",
            "MEALMATE_ROOT": str(pi.root),
            "MEALMATE_IMAGE": pi.image,
            "MEALMATE_SKIP_SYSTEM": "1",
            "MEALMATE_SYSTEMD_DIR": str(base / "systemd"),
            "MEALMATE_TAILSCALE_STATE_DIR": str(ts),
            "MEALMATE_SSH_DIR": str(ssh),
            "MEALMATE_BACKUP_USER": "root",
            "MEALMATE_BACKUP_GROUP": "root",
            "MEALMATE_BACKUP_HOME": str(home),
            "MEALMATE_LOCAL_URL": f"http://127.0.0.1:{port}",
            "MEALMATE_HEALTH_TIMEOUT": "90",
            # Stable health: 3 good checks 1 s apart (10 s on the Pi) keeps the suite quick.
            "MEALMATE_HEALTH_STABLE_INTERVAL": "1",
            "MEALMATE_HEALTH_POLL_INTERVAL": "1",
            "MEALMATE_PRECHECK_TIMEOUT": "30",
            "MEALMATE_COSIGN_RETRY_DELAY": "0",
            "APT_GET": str(shims / "apt-get"),
            "COSIGN": str(shims / "cosign"),
            "TAILSCALE": str(shims / "tailscale"),
            "SYSTEMCTL": str(shims / "systemctl"),
            "COMPOSE_FILE": "compose.yml:compose.test.yml",
            "COMPOSE_PROJECT_NAME": pi.name,
            "MM_TEST_CALLS": str(base / "calls.log"),
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
        if env_file:
            write_env(pi)
        created.append(pi)
        return pi

    yield make
    for pi in created:
        pi.remove_containers()


def tree(directory: Path) -> dict[str, bytes]:
    """Relative path → content of every regular file below `directory`."""
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }


# --- bash 3.2 for the Mac scripts -------------------------------------------------------------


@pytest.fixture(scope="session")
def mac_bash(tmp_path_factory: pytest.TempPathFactory) -> str:
    """A bash 3.2 (what macOS ships), run on this host through the musl loader of bash:3.2."""
    if os.environ.get("MM_TEST_MAC_BASH"):
        return os.environ["MM_TEST_MAC_BASH"]
    if not docker_ok():
        pytest.skip("Docker is needed to provide bash 3.2")
    directory = tmp_path_factory.mktemp("bash32")
    cid = run(["docker", "create", BASH32_IMAGE], timeout=300).stdout.strip()
    try:
        run(["docker", "cp", "-L", f"{cid}:/usr/local/bin/bash", str(directory / "bash")])
        run(["docker", "cp", "-L", f"{cid}:/lib", str(directory / "lib")])
        run(["docker", "cp", "-L", f"{cid}:/usr/lib/libncursesw.so.6", str(directory / "lib")])
    finally:
        run(["docker", "rm", cid], check=False)
    loader = next((directory / "lib").glob("ld-musl-*.so.1"))
    wrapper = directory / "bash3"
    libs, bash = directory / "lib", directory / "bash"
    wrapper.write_text(
        f'#!/bin/sh\nexec "{loader}" --library-path "{libs}" "{bash}" "$@"\n', encoding="utf-8"
    )
    wrapper.chmod(0o755)
    version = run([wrapper, "-c", "echo $BASH_VERSION"]).stdout
    assert version.startswith("3.2"), version
    return str(wrapper)
