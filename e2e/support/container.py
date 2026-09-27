"""Runs the production image for the suite, hardened like deploy/compose.yml."""

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

CONTAINER_PORT = 8080


class AppStartError(RuntimeError):
    """The container exited or never became healthy."""


@dataclass(frozen=True)
class AppContainer:
    container_id: str
    base_url: str

    def logs(self) -> str:
        result = subprocess.run(
            ["docker", "logs", self.container_id],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout + result.stderr

    def is_running(self) -> bool:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", self.container_id],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() == "true"

    def exec(self, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        """Runs a command inside the container (as its app user), e.g. the `mealmate` CLI."""
        command = ["docker", "exec", *(["--interactive"] if stdin is not None else [])]
        return subprocess.run(
            [*command, self.container_id, *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
        )

    def stop(self) -> None:
        # Started with --rm, so stopping also removes it.
        subprocess.run(
            ["docker", "stop", "--time", "5", self.container_id],
            capture_output=True,
            check=False,
        )


def start_app(image: str, port: int, env: dict[str, str]) -> AppContainer:
    """Starts `image` on 127.0.0.1:`port` with an empty tmpfs /data."""
    command = [
        "docker",
        "run",
        "--detach",
        "--rm",
        "--publish",
        f"127.0.0.1:{port}:{CONTAINER_PORT}",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--tmpfs",
        "/data:uid=10001,gid=10001,mode=0700",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
    ]
    for name, value in env.items():
        command += ["--env", f"{name}={value}"]
    command.append(image)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AppStartError(f"docker run {image} failed:\n{result.stderr.strip()}")
    return AppContainer(container_id=result.stdout.strip(), base_url=f"http://127.0.0.1:{port}")


def wait_until_healthy(app: AppContainer, timeout: float = 60.0) -> None:
    """Polls /api/health until it answers 200; fails early if the container exits."""
    deadline = time.monotonic() + timeout
    # trust_env=False: never send loopback requests through a proxy from the environment.
    with httpx.Client(base_url=app.base_url, timeout=2.0, trust_env=False) as client:
        while time.monotonic() < deadline:
            try:
                if client.get("/api/health").status_code == 200:
                    return
            except httpx.TransportError:
                pass
            if not app.is_running():
                raise AppStartError(f"the app container exited during startup:\n{app.logs()}")
            time.sleep(0.5)
    raise AppStartError(f"/api/health not ready after {timeout:.0f} s:\n{app.logs()}")


def save_logs(app: AppContainer, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(app.logs(), encoding="utf-8")
