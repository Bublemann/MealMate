"""Serves the Open Food Facts stand-in (fake_off/) to the app container of the suite.

The app contacts Open Food Facts from the server only (SEC-08), so the stand-in must be reachable
from inside the container: the container reaches the host through Docker's bridge as
`host.docker.internal`. The stand-in listens only on the bridge's gateway address (`docker0`,
e.g. 172.17.0.1, from `docker network inspect bridge`), which the container's
`--add-host host.docker.internal:<gateway>` then names; other networks can't reach it. Where
that address is not one of this host's (Docker Desktop, rootless Docker), it falls back to all
interfaces and `host-gateway`. On GitHub's Ubuntu runners `host-gateway` is `docker0` as well.
"""

import ipaddress
import json
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import uvicorn

from fake_off.app import app

CONTAINER_HOST = "host.docker.internal"
ALL_INTERFACES = "0.0.0.0"  # noqa: S104 -- only the fallback, see bridge_gateway()
HOST_GATEWAY = "host-gateway"


def bridge_gateway() -> str | None:
    """The IPv4 gateway of Docker's default bridge, if it is an address of this host."""
    try:
        result = subprocess.run(
            ["docker", "network", "inspect", "bridge", "--format", "{{json .IPAM.Config}}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        configs = json.loads(result.stdout) or []
        gateways = [ipaddress.ip_address(config["Gateway"]) for config in configs]
    except (OSError, subprocess.SubprocessError, ValueError, LookupError, TypeError):
        return None
    gateway = next((str(address) for address in gateways if address.version == 4), None)
    if gateway is None:
        return None
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((gateway, 0))
    except OSError:
        return None
    return gateway


@dataclass(frozen=True)
class FakeOff:
    port: int
    # What `host.docker.internal` stands for in the container (`--add-host`).
    host_address: str

    @property
    def url_in_container(self) -> str:
        """The base URL the app container uses (MEALMATE_OFF_BASE_URL)."""
        return f"http://{CONTAINER_HOST}:{self.port}"


@contextmanager
def serve_fake_off() -> Iterator[FakeOff]:
    """Runs the stand-in on a free port of the bridge's gateway until the block ends."""
    gateway = bridge_gateway()
    config = uvicorn.Config(app, host=gateway or ALL_INTERFACES, port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the fake Open Food Facts server did not start")
        time.sleep(0.01)
    try:
        yield FakeOff(
            port=server.servers[0].sockets[0].getsockname()[1],
            host_address=gateway or HOST_GATEWAY,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
